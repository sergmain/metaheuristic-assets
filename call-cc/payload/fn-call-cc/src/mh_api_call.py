# The Anthropic Messages API path of mh.asset.call-cc (process meta llm_provider = "claude_api").
#
# The CC path hands the prompt to the Claude Code CLI and takes back what the model stored through this Function's MCP
# tool mh_cc_store_result. This path keeps that contract over the plain Messages API: the request offers the SAME tool
# (same name, one string parameter `result`) and forces it with tool_choice, so
#
#   - a prompt written for the CC path ("store your answer with mh_cc_store_result") works unchanged, and
#   - the answer is still exactly one tool call's `result`, copied verbatim - never the model's free text.
#
# A model that refuses a forced tool_choice (the API's 400 naming tool_choice - claude-sonnet-5-5, plan 050 Phase 17)
# gets the same request once more with tool_choice auto: the tool still offered, the prompt still asking for it, and
# the answer still exactly one store call (answer_from_response) - free text is refused as before.
#
# The API key is never in argv, env or on disk: the Processor seals the Vault entry named by mh-function.yaml's
# api.keyCode and hands it over its loopback secret channel, whose port and check code are in the params file
# (task.secretPort, task.checkCode). read_secret() speaks that protocol - big-endian int32 length frames: send the check
# code, read the key - and the caller zeroes the bytes when the call is done.
#
# The core - store_result_tool / request_body / answer_from_response / api_failure_line - is pure and is what
# call-cc/tests exercises; read_secret and post_messages are the two boundary calls, each exercised there against a
# local socket / HTTP server.

import json
import socket
import struct
import urllib.error
import urllib.request

API_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_VERSION = '2023-06-01'

# Output budget of one call; overridable per process with meta 'max-tokens'. An answer cut at the budget is a failure
# (see answer_from_response), never a shorter answer.
DEFAULT_MAX_TOKENS = 8192

# The tool the model must call - the same name the CC path's MCP server exposes, so one prompt serves both paths.
STORE_RESULT_TOOL = 'mh_cc_store_result'

# How much of a failed response's body is printed. The dispatcher's analyzers match the console, so the status line
# and the API's own error type must be in it; the whole body need not be.
MAX_BODY_SNIPPET = 2000

# The loopback secret channel: one frame each way, a sane cap on the key frame.
MAX_KEY_FRAME_BYTES = 65536
SECRET_TIMEOUT_SEC = 5


# ---------------------------------------------------------------------------------------------------
# THE REQUEST

def store_result_tool():
    """The tool definition offered to the model: the API twin of the MCP tool mh_cc_store_result."""
    return {
        'name': STORE_RESULT_TOOL,
        'description': 'Store the final answer of this task. Call it exactly once, with the complete answer as '
                       'the result argument. Whatever is not passed here is lost.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'result': {'type': 'string', 'description': 'The complete answer, exactly as the task asks for it.'},
            },
            'required': ['result'],
        },
    }


def request_body(model, prompt, max_tokens, forced=True):
    """The Messages API request: one user turn with the prompt verbatim, the store tool offered - forced, or with
    forced=False offered under tool_choice auto (a model that refuses forced tool use - tool_choice_refused)."""
    if model is None or not model.strip():
        raise ValueError('a model is required on the claude_api path - the API has no default model')
    if max_tokens < 1:
        raise ValueError('max-tokens must be greater than 0, got ' + str(max_tokens))
    return {
        'model': model.strip(),
        'max_tokens': max_tokens,
        'messages': [{'role': 'user', 'content': prompt}],
        'tools': [store_result_tool()],
        'tool_choice': {'type': 'tool', 'name': STORE_RESULT_TOOL} if forced else {'type': 'auto'},
    }


def tool_choice_refused(status, text):
    """Whether a response is the API refusing the request's forced tool_choice for this model: a 400 whose error body is
    an invalid_request_error naming tool_choice. Any other failure is not - it stays a failed call."""
    if status != 400 or not text:
        return False
    try:
        error = (json.loads(text) or {}).get('error') or {}
    except ValueError:
        return False
    return error.get('type') == 'invalid_request_error' and 'tool_choice' in str(error.get('message'))


def max_tokens(metas_value):
    """Meta 'max-tokens' as an int, DEFAULT_MAX_TOKENS when absent or blank."""
    if metas_value is None or not metas_value.strip():
        return DEFAULT_MAX_TOKENS
    value = int(metas_value.strip())
    if value < 1:
        raise ValueError('max-tokens must be greater than 0, got ' + str(value))
    return value


# ---------------------------------------------------------------------------------------------------
# THE RESPONSE

def answer_from_response(envelope):
    """The `result` of the one mh_cc_store_result call in a 2xx response envelope (a parsed dict).

    Fails rather than guessing:
      - stop_reason max_tokens: the tool input was cut at the budget, so the answer is incomplete;
      - no mh_cc_store_result call, or more than one;
      - a result that is not a string, or is blank - the same refusal the MCP server makes for an empty store.
    """
    stop_reason = envelope.get('stop_reason')
    if stop_reason == 'max_tokens':
        raise ValueError('the response hit max_tokens - the answer is cut off. Raise meta max-tokens (was '
                         + str(envelope.get('usage', {}).get('output_tokens')) + ' output tokens)')
    calls = [b for b in envelope.get('content') or []
             if isinstance(b, dict) and b.get('type') == 'tool_use' and b.get('name') == STORE_RESULT_TOOL]
    if len(calls) != 1:
        kinds = [str(b.get('type')) for b in envelope.get('content') or [] if isinstance(b, dict)]
        raise ValueError('expected exactly one ' + STORE_RESULT_TOOL + ' call, got ' + str(len(calls))
                         + '; stop_reason=' + str(stop_reason) + ', blocks=' + str(kinds))
    result = (calls[0].get('input') or {}).get('result')
    if not isinstance(result, str):
        raise ValueError(STORE_RESULT_TOOL + ' was called without a string result, got ' + type(result).__name__)
    if not result.strip():
        raise ValueError(STORE_RESULT_TOOL + ' was called with an empty result - there is nothing to store')
    return result


def api_failure_line(status, body):
    """The console line for a non-2xx response. The analyzers in mh-function.yaml match its wording - keep it."""
    snippet = '<no body>' if body is None else (body[:MAX_BODY_SNIPPET] + '...' if len(body) > MAX_BODY_SNIPPET else body)
    return 'Anthropic API call failed with status ' + str(status) + '; body=' + snippet


# ---------------------------------------------------------------------------------------------------
# THE BOUNDARY

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
    """Overwrite a key buffer in place."""
    for i in range(len(buf)):
        buf[i] = 0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # a 3xx is a failed call, not a new request - the key header must never follow a redirect
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_messages(url, api_key, body, timeout_sec):
    """One POST of `body` (a dict) to the Messages API: (status, response text). Non-2xx is returned, not raised."""
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(url, data=data, method='POST', headers={
        'content-type': 'application/json',
        'anthropic-version': ANTHROPIC_VERSION,
        'x-api-key': api_key,
    })
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout_sec) as response:
            return response.status, _decode(response)
    except urllib.error.HTTPError as e:
        return e.code, _decode(e)


def _decode(response):
    charset = response.headers.get_content_charset() or 'utf-8'
    return response.read().decode(charset, errors='replace')
