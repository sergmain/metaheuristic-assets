# The Anthropic Messages API path of mh.asset.nrvv-implement (process meta llm_provider = "claude_api"), plan 052
# Phase 3.
#
# The CC path runs ONE Claude Code session in the target dir with Read, Write, Edit, Glob, Grep and
# Bash(python -m pytest:*). This path keeps that session's shape over the plain Messages API: a tool loop whose tools
# ARE that confinement -
#
#   list_files / read_file / write_file / edit_file   inside the target dir only: a relative path, no '..', and a
#                                                      realpath that stays under the target dir
#   run_tests                                          exactly the prompt's command, python -m pytest <test-suite dir>
#                                                      -q [tests/<file>.py], with the session environment
#
# - and the same prompt, byte for byte. The loop ends when the model ends its turn without a tool call; its text is
# the summary, as the CC session's final message is. It verifies nothing: mh.asset.nrvv-guard checks where it wrote and
# the verification run checks what it wrote, exactly as after a CC session.
#
# The key is never in argv, env or on disk: the Processor hands it over its loopback secret channel (task.secretPort,
# task.checkCode) for a code whose mh-function.yaml declares api.keyCode, and it is zeroed after the loop.
#
# The core - tool_definitions / confined / run_tool / first_request / tool_uses / final_text / next_messages / run_loop
# - is testable without a Processor; run_loop takes `post` as a parameter, so production passes the real HTTPS call
# and a test passes something else. read_secret / post_messages / pytest_runner are the boundary.

import json
import os
import socket
import struct
import subprocess
import time
import urllib.error
import urllib.request

API_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_VERSION = '2023-06-01'

LLM_PROVIDER_META = 'llm_provider'
PROVIDER_CC = 'cc'
PROVIDER_CLAUDE_API = 'claude_api'

DEFAULT_MAX_TURNS = 60
# a whole module is written in ONE tool call, so the budget of a call is larger than call-cc's
DEFAULT_MAX_TOKENS = 16000
# what one tool result may carry back into the conversation; the head and the tail of a longer one are kept
MAX_TOOL_RESULT_CHARS = 20000
# one HTTP call never waits longer than this, whatever is left of the session's timeout
MAX_CALL_SECONDS = 600
MAX_BODY_SNIPPET = 2000
MAX_KEY_FRAME_BYTES = 65536
SECRET_TIMEOUT_SEC = 5
SKIPPED_DIRS = ('__pycache__', '.git', '.pytest_cache')
# The response headers that say WHICH limit a 429 hit (https://platform.claude.com/docs/en/api/rate-limits#response-headers):
# the request limit and the token limits answer the same status and error type, and only these tell them apart. The
# Processor sees nothing of the HTTP exchange - only this Function's console - so the Function prints them, and MH's
# shipped analyzers (mh-api-analyzers.yaml, rule api-request-limit) match the lines. The format is a contract: one
# '<header>: <value>' line each, name in lower case, in this order, an absent header omitted.
RATE_LIMIT_HEADERS = ('retry-after', 'anthropic-ratelimit-requests-remaining', 'anthropic-ratelimit-tokens-remaining',
                      'anthropic-ratelimit-input-tokens-remaining', 'anthropic-ratelimit-output-tokens-remaining')


class ToolError(Exception):
    """A tool call that cannot be carried out - reported to the model as an error result, never raised further."""


class AgentError(Exception):
    """The loop cannot go on: the Function fails with this message."""


def llm_provider(value):
    """The value of meta llm_provider: PROVIDER_CC when absent or blank; anything but the two known values fails."""
    if value is None or not str(value).strip():
        return PROVIDER_CC
    value = str(value).strip()
    if value not in (PROVIDER_CC, PROVIDER_CLAUDE_API):
        raise ValueError("meta '" + LLM_PROVIDER_META + "' must be '" + PROVIDER_CC + "' or '" + PROVIDER_CLAUDE_API
                         + "', got '" + value + "'")
    return value


def positive_int(value, default, name):
    if value is None or not str(value).strip():
        return default
    number = int(str(value).strip())
    if number < 1:
        raise ValueError(name + ' must be greater than 0, got ' + str(number))
    return number


# ---------------------------------------------------------------------------------------------------
# THE TOOLS

def tool_definitions():
    path = {'type': 'string', 'description': 'A path relative to the current (target) directory.'}
    return [
        {'name': 'list_files', 'description': 'List the files under a directory of the target directory, recursively.',
         'input_schema': {'type': 'object', 'properties': {'path': dict(path, description='A directory relative to '
                          'the target directory; "." or absent is the target directory itself.')}}},
        {'name': 'read_file', 'description': 'Read a file of the target directory.',
         'input_schema': {'type': 'object', 'properties': {'path': path}, 'required': ['path']}},
        {'name': 'write_file', 'description': 'Create or overwrite a file of the target directory with the whole '
                                              'content given; parent directories are created.',
         'input_schema': {'type': 'object', 'properties': {'path': path, 'content': {'type': 'string'}},
                          'required': ['path', 'content']}},
        {'name': 'edit_file', 'description': 'Replace the one occurrence of old with new in a file of the target '
                                             'directory; old must occur exactly once.',
         'input_schema': {'type': 'object', 'properties': {'path': path, 'old': {'type': 'string'},
                                                           'new': {'type': 'string'}},
                          'required': ['path', 'old', 'new']}},
        {'name': 'run_tests', 'description': 'Run the command the task names: python -m pytest <test-suite dir> -q, '
                                             'or one test file with it. Returns the exit code and the output.',
         'input_schema': {'type': 'object', 'properties': {'file': {'type': 'string', 'description':
                          'Optional: one test file, tests/<file>.py, relative to the test-suite directory.'}}}},
    ]


def confined(root, rel):
    """The absolute path of `rel` inside `root`, or a ToolError: a blank or absolute path, a '..' escape, and a link
    whose target lies outside are all refused - the check is on the realpath, not on the spelling."""
    if not isinstance(rel, str) or not rel.strip():
        raise ToolError('a path is required')
    rel = rel.strip()
    if os.path.isabs(rel) or os.path.splitdrive(rel)[0] or rel.startswith(('/', '\\')):
        raise ToolError('only a path relative to the target directory is allowed: ' + rel)
    root_real = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_real, rel))
    if os.path.commonpath([candidate, root_real]) != root_real:
        raise ToolError('the path leaves the target directory: ' + rel)
    return candidate


def clip(text, limit=MAX_TOOL_RESULT_CHARS):
    if len(text) <= limit:
        return text
    head = limit // 5
    return text[:head] + '\n... ' + str(len(text) - limit) + ' chars omitted ...\n' + text[-(limit - head):]


def list_files(target_dir, rel):
    root = confined(target_dir, rel if rel and str(rel).strip() else '.')
    if not os.path.isdir(root):
        raise ToolError('not a directory: ' + str(rel))
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIPPED_DIRS)
        for name in sorted(filenames):
            found.append(os.path.relpath(os.path.join(dirpath, name), os.path.realpath(target_dir)).replace('\\', '/'))
    return '\n'.join(found) if found else '(no files)'


def run_tool(name, args, target_dir, run_tests):
    """(result text, is_error) of one tool call. run_tests(file or None) -> text is the suite runner."""
    args = args if isinstance(args, dict) else {}
    try:
        if name == 'list_files':
            return list_files(target_dir, args.get('path')), False
        if name == 'read_file':
            path = confined(target_dir, args.get('path'))
            if not os.path.isfile(path):
                raise ToolError('no such file: ' + str(args.get('path')))
            with open(path, encoding='utf-8', newline='') as f:
                return clip(f.read()), False
        if name == 'write_file':
            path = confined(target_dir, args.get('path'))
            content = args.get('content')
            if not isinstance(content, str):
                raise ToolError('content must be a string')
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(content)
            return 'wrote ' + str(len(content.encode('utf-8'))) + ' bytes to ' + args.get('path').strip(), False
        if name == 'edit_file':
            path = confined(target_dir, args.get('path'))
            old, new = args.get('old'), args.get('new')
            if not isinstance(old, str) or not old or not isinstance(new, str):
                raise ToolError('old must be a non-empty string and new a string')
            if not os.path.isfile(path):
                raise ToolError('no such file: ' + str(args.get('path')))
            with open(path, encoding='utf-8', newline='') as f:
                text = f.read()
            if text.count(old) != 1:
                raise ToolError('old occurs ' + str(text.count(old)) + ' times, it must occur exactly once')
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(text.replace(old, new))
            return 'edited ' + args.get('path').strip(), False
        if name == 'run_tests':
            file = args.get('file')
            return clip(run_tests(file.strip() if isinstance(file, str) and file.strip() else None)), False
        raise ToolError('no such tool: ' + str(name))
    except ToolError as e:
        return 'error: ' + str(e), True


# ---------------------------------------------------------------------------------------------------
# THE CONVERSATION

def first_request(model, prompt, max_tokens):
    """The first request: the prompt as the one user block, marked for prompt caching - it is resent every turn."""
    if model is None or not model.strip():
        raise ValueError('a model is required on the claude_api path - the API has no default model')
    return {
        'model': model.strip(),
        'max_tokens': max_tokens,
        'tools': tool_definitions(),
        'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': prompt,
                                                   'cache_control': {'type': 'ephemeral'}}]}],
    }


def tool_uses(envelope):
    return [b for b in envelope.get('content') or [] if isinstance(b, dict) and b.get('type') == 'tool_use']


def final_text(envelope):
    return '\n'.join(b.get('text') for b in envelope.get('content') or []
                     if isinstance(b, dict) and b.get('type') == 'text' and b.get('text')).strip()


def next_messages(messages, envelope, results):
    """messages + the assistant turn as it came + one user turn holding a tool_result per tool call, in order."""
    return messages + [
        {'role': 'assistant', 'content': envelope.get('content') or []},
        {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': use_id, 'content': text,
                                      'is_error': is_error} for use_id, text, is_error in results]},
    ]


def api_failure_line(status, body):
    """The line for a non-2xx response; mh-function.yaml's analyzers match its wording - keep it."""
    snippet = '<no body>' if body is None else (body[:MAX_BODY_SNIPPET] + '...' if len(body) > MAX_BODY_SNIPPET else body)
    return 'Anthropic API call failed with status ' + str(status) + '; body=' + snippet


def rate_limit_header_lines(headers):
    """One '<header>: <value>' line per rate-limit header present, in RATE_LIMIT_HEADERS order. `headers` is anything
    with a case-insensitive get() - an HTTPError's headers are."""
    if headers is None:
        return []
    lines = []
    for name in RATE_LIMIT_HEADERS:
        value = headers.get(name)
        if value is not None:
            lines.append(name + ': ' + str(value).strip())
    return lines


def run_loop(post, body, target_dir, run_tests, max_turns, deadline, now=time.monotonic, log=print):
    """The session: post(body, seconds) -> (status, text) until the model ends its turn without a tool call; returns
    its final text. An AgentError for a non-2xx response, an answer cut at max_tokens, max_turns spent or the deadline
    (a now() value) passed."""
    messages = body['messages']
    for turn in range(1, max_turns + 1):
        left = deadline - now()
        if left <= 0:
            raise AgentError('the session did not finish within its timeout, after ' + str(turn - 1) + ' turn(s)')
        status, text = post(dict(body, messages=messages), min(left, MAX_CALL_SECONDS))
        if status < 200 or status >= 300:
            raise AgentError(api_failure_line(status, text))
        envelope = json.loads(text)
        if envelope.get('stop_reason') == 'max_tokens':
            raise AgentError('turn ' + str(turn) + ' hit max_tokens - a tool call was cut off. Raise meta max-tokens')
        uses = tool_uses(envelope)
        log('turn ' + str(turn) + ': stop_reason ' + str(envelope.get('stop_reason')) + ', tool calls '
            + str([u.get('name') for u in uses]) + ', usage ' + json.dumps(envelope.get('usage')))
        if not uses:
            return final_text(envelope)
        results = [(u.get('id'), *run_tool(u.get('name'), u.get('input'), target_dir, run_tests)) for u in uses]
        messages = next_messages(messages, envelope, results)
    raise AgentError('the session used all ' + str(max_turns) + ' turns without finishing. Raise meta max-turns')


# ---------------------------------------------------------------------------------------------------
# THE BOUNDARY

def pytest_runner(python_exec, test_suite_dir, target_dir, env, timeout_sec=600):
    """run_tests for run_tool: the prompt's command, in the target dir, with the session environment."""
    def run_tests(file):
        command = [python_exec, '-m', 'pytest', test_suite_dir, '-q']
        if file is not None:
            path = confined(test_suite_dir, file)
            if not os.path.isfile(path):
                raise ToolError('no such test file in the test-suite directory: ' + file)
            command = [python_exec, '-m', 'pytest', path, '-q']
        try:
            completed = subprocess.run(command, cwd=target_dir, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            raise ToolError('the tests did not finish within ' + str(timeout_sec) + 's')
        output = completed.stdout.decode('utf-8', errors='replace') if completed.stdout else ''
        return 'exit code ' + str(completed.returncode) + '\n' + output
    return run_tests


def read_secret(port, check_code, timeout_sec=SECRET_TIMEOUT_SEC):
    """The key from the Processor's loopback secret channel, as a bytearray the caller zeroes after use."""
    with socket.create_connection(('127.0.0.1', int(port)), timeout=timeout_sec) as sock:
        sock.settimeout(timeout_sec)
        code = str(check_code).encode('utf-8')
        sock.sendall(struct.pack('>i', len(code)) + code)
        (length,) = struct.unpack('>i', bytes(_read_exactly(sock, 4)))
        if length < 0 or length > MAX_KEY_FRAME_BYTES:
            raise OSError('invalid key frame length from the secret channel: ' + str(length))
        return _read_exactly(sock, length)


def _read_exactly(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise EOFError('the secret channel closed after ' + str(len(buf)) + ' of ' + str(n)
                           + ' bytes - a wrong check code gets no key')
        buf.extend(chunk)
    return buf


def zero(buf):
    for i in range(len(buf)):
        buf[i] = 0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # a 3xx is a failed call, not a new request - the key header must never follow a redirect
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_messages(url, api_key, body, timeout_sec):
    """One POST to the Messages API: (status, response text). Non-2xx is returned, not raised."""
    request = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), method='POST',
                                     headers={'content-type': 'application/json',
                                              'anthropic-version': ANTHROPIC_VERSION, 'x-api-key': api_key})
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout_sec) as response:
            return response.status, _decode(response)
    except urllib.error.HTTPError as e:
        # the only moment the headers exist: print what tells a request limit from a token limit (see RATE_LIMIT_HEADERS)
        for line in rate_limit_header_lines(e.headers):
            print(line, flush=True)
        return e.code, _decode(e)


def _decode(response):
    return response.read().decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
