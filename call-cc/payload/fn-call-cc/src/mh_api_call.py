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
# The run's effort is the API's extended thinking (plan 050 Phase 17: every v5 - v7 analysis of r1 on the CC path, effort
# high, read "Stations act on stale prices." as a fact or a cost; four of five v8 analyses on the API path with the effort
# dropped read it as an obligation). Thinking excludes a forced tool, so a request with thinking offers the tool under
# tool_choice auto, its max_tokens the answer's budget plus the thinking budget. A model refusing the thinking parameter
# (a 400 naming thinking) gets the request once more without it.
#
# (Superseded 2026-10-25, plan 050 Phase 17, by the API's thinking documentation - the two paragraphs above are kept per
# the no-delete rule.) The store tool is offered under tool_choice auto on EVERY request: a forced tool_choice starts a
# Claude Haiku 5.5 response with the tool call and no thinking block (v8's analyses #101 - #106 ran with 0 thinking
# tokens), and Claude Opus 5.5 / Sonnet 5.5 refuse it with a 400. No thinking field is sent: thinking is adaptive by
# default on the 5.5 models, and thinking.type "enabled" with budget_tokens is a 400 there. The run's effort is sent as
# output_config.effort (api_effort: the wire code, extra -> xhigh); max_tokens adds room for the thinking, which counts
# toward it. A refused request is never retried without what it refused - a run without its effort or thinking is a
# different run, and the silent fallback is what hid this in #106; it fails with the API's message (refused_parameter).
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

# The extended-thinking budget per effort - the model's reasoning before it answers (plan 050 Phase 17).
THINKING_BUDGET = {'low': 2048, 'medium': 6144, 'high': 12288, 'xhigh': 24576, 'extra': 24576}

# (plan 050 Phase 17, 2026-10-25) THINKING_BUDGET above is no longer sent - see the superseded note at the top.
# The API's output_config.effort per wire code (RG's RgLlmEffort.code, case-insensitive): low, medium, high and max are the
# API's own; extra is the API's xhigh, as it is CC's; xhigh is accepted as itself.
API_EFFORT = {'low': 'low', 'medium': 'medium', 'high': 'high', 'extra': 'xhigh', 'xhigh': 'xhigh', 'max': 'max'}

# Room for adaptive thinking on top of the answer's budget, per API effort - thinking counts toward max_tokens, and an
# answer cut at max_tokens is a failure (answer_from_response). Room the model does not use costs nothing.
THINKING_ROOM = {'low': 8192, 'medium': 16384, 'high': 32768, 'xhigh': 65536, 'max': 65536}

# The room when the run names no effort: the 5.5 models then run at their default effort, medium or high.
DEFAULT_THINKING_ROOM = THINKING_ROOM['high']

# The request's max_tokens is capped at the models' output ceiling (128K on Claude Haiku 5.5, Sonnet 5.5 and Opus 5.5).
MAX_OUTPUT_TOKENS = 128000

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


def request_body(model, prompt, max_tokens, effort=None):
    """The Messages API request: one user turn with the prompt verbatim, the store tool offered - forced, or with
    forced=False offered under tool_choice auto (a model that refuses forced tool use - tool_choice_refused). With a
    thinking budget: extended thinking on, max_tokens the answer's budget plus the thinking budget, the tool under auto.

    (Superseded 2026-10-25, plan 050 Phase 17 - the paragraph above is kept per the no-delete rule; there is no forced
    and no thinking parameter any more.) The store tool is offered under tool_choice auto, always, and no thinking field
    is sent. effort - an API effort (api_effort) or None - is sent as output_config.effort. max_tokens is the answer's
    budget; the request's max_tokens adds thinking_room(effort), capped at MAX_OUTPUT_TOKENS."""
    if model is None or not model.strip():
        raise ValueError('a model is required on the claude_api path - the API has no default model')
    if max_tokens < 1:
        raise ValueError('max-tokens must be greater than 0, got ' + str(max_tokens))
    body = {
        'model': model.strip(),
        'max_tokens': min(max_tokens + thinking_room(effort), MAX_OUTPUT_TOKENS),
        'messages': [{'role': 'user', 'content': prompt}],
        'tools': [store_result_tool()],
        'tool_choice': {'type': 'auto'},
    }
    if effort is not None:
        body['output_config'] = {'effort': effort}
    return body


def thinking_budget(effort):
    """The extended-thinking budget of an effort (THINKING_BUDGET), None for no effort; an unknown effort is refused."""
    if effort is None or not effort.strip():
        return None
    budget = THINKING_BUDGET.get(effort.strip().lower())
    if budget is None:
        raise ValueError('unknown effort ' + repr(effort) + ' on the claude_api path - one of ' + str(sorted(THINKING_BUDGET)))
    return budget


def api_effort(effort):
    """The API's output_config.effort of a run's effort (its wire code, API_EFFORT), None for no effort; an unknown effort
    is refused (plan 050 Phase 17)."""
    if effort is None or not effort.strip():
        return None
    value = API_EFFORT.get(effort.strip().lower())
    if value is None:
        raise ValueError('unknown effort ' + repr(effort) + ' on the claude_api path - one of ' + str(sorted(API_EFFORT)))
    return value


def thinking_room(effort):
    """The max_tokens room for adaptive thinking of an API effort (THINKING_ROOM), DEFAULT_THINKING_ROOM for None; an
    effort that is not an API effort (a wire code such as extra included) is refused."""
    if effort is None:
        return DEFAULT_THINKING_ROOM
    room = THINKING_ROOM.get(effort)
    if room is None:
        raise ValueError('unknown API effort ' + repr(effort) + ' - one of ' + str(sorted(THINKING_ROOM)))
    return room


def _refusal_names(status, text, word):
    """Whether a response is the API's 400 invalid_request_error whose message names `word`."""
    if status != 400 or not text:
        return False
    try:
        error = (json.loads(text) or {}).get('error') or {}
    except ValueError:
        return False
    return error.get('type') == 'invalid_request_error' and word in str(error.get('message'))


def thinking_refused(status, text):
    """Whether a response is the API refusing the request's extended thinking for this model."""
    return _refusal_names(status, text, 'thinking')


def api_error_message(text):
    """The API's own error message of a failed response (its error.message), else the body's first MAX_BODY_SNIPPET chars."""
    try:
        message = ((json.loads(text) or {}).get('error') or {}).get('message')
    except (ValueError, TypeError):
        message = None
    if message:
        return str(message)
    return '<no body>' if not text else text[:MAX_BODY_SNIPPET]


def tool_choice_refused(status, text):
    """Whether a response is the API refusing the request's forced tool_choice for this model: a 400 whose error body is
    an invalid_request_error naming tool_choice. Any other failure is not - it stays a failed call."""
    return _refusal_names(status, text, 'tool_choice')


def refused_parameter(status, text):
    """The request parameter a 400 invalid_request_error names - tool_choice, thinking, effort or output_config, the first
    one named - else None. For the console only: a refusal is never retried without the parameter (plan 050 Phase 17)."""
    for word in ('tool_choice', 'thinking', 'effort', 'output_config'):
        if _refusal_names(status, text, word):
            return word
    return None


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
