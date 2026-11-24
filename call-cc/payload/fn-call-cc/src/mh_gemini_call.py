# The Google Gemini API path of mh.asset.call-cc (process meta llm_provider = "gemini_api").
#
# The same contract as the Anthropic path (mh_api_call): the request offers the store tool mh_cc_store_result (one
# string parameter `result`) - declared as a functionDeclarations entry, under functionCallingConfig mode AUTO as the
# Anthropic path offers it under tool_choice auto - so a prompt written for the CC path ("store your answer with
# mh_cc_store_result") works unchanged, and the answer is still exactly one call's `result`, copied verbatim - never the
# model's free text.
#
# The shapes were confirmed against the live API (2026-11-23, gemini-3.5-flash-lite):
#   request   POST .../v1beta/models/<model>:generateContent, header x-goog-api-key,
#             {"contents": [{"role": "user", "parts": [{"text": ...}]}], "tools": [{"functionDeclarations": [...]}],
#              "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}}, "generationConfig": {...}}
#   answer    candidates[0].content.parts: one {"functionCall": {"name": "mh_cc_store_result", "args": {"result": ...},
#             "id": ...}, "thoughtSignature": ...}, finishReason STOP
#   usage     usageMetadata {promptTokenCount, candidatesTokenCount, totalTokenCount, ...}
#   failure   {"error": {"code": 404, "message": "...", "status": "NOT_FOUND"}}, pretty-printed
#
# The run's effort is Gemini's own thinkingLevel - MINIMAL, LOW, MEDIUM or HIGH, as RG resolves it for a Gemini model -
# sent as generationConfig.thinkingConfig.thinkingLevel; no effort sends no thinkingConfig and the API's default applies.
# maxOutputTokens is the answer's budget plus room for the thinking (THINKING_ROOM) - room the model does not use costs
# nothing. (Whether Gemini counts its thinking toward maxOutputTokens is not verified; the room covers the case it does.)
#
# The API key is never in argv, env or on disk: the Processor seals the Vault entry named by mh-function.yaml's
# api.keyCode (GEMINI_API_KEY) and hands it over its loopback secret channel - mh_api_call.read_secret speaks that
# protocol, the caller zeroes the bytes when the call is done.
#
# The core - store_result_declaration / request_body / thinking_level / answer_from_response / api_failure_line - is pure
# and is what call-cc/tests exercises; post_generate_content is the boundary, exercised there against a local server.

import json
import urllib.error
import urllib.parse
import urllib.request

from mh_api_call import MAX_BODY_SNIPPET, STORE_RESULT_TOOL

# The model id goes between this and ":generateContent".
API_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/models/'

# The API's thinkingLevel values, in RG's display order (RgLlmModel.GEMINI_3_5_FLASH_LITE).
THINKING_LEVELS = ('MINIMAL', 'LOW', 'MEDIUM', 'HIGH')

# Room for the thinking on top of the answer's budget, per thinkingLevel; DEFAULT_THINKING_ROOM when the run names none.
THINKING_ROOM = {'MINIMAL': 2048, 'LOW': 8192, 'MEDIUM': 16384, 'HIGH': 32768}
DEFAULT_THINKING_ROOM = THINKING_ROOM['MINIMAL']

# The request's maxOutputTokens is capped at the model's output ceiling (65536 - not verified on 3.5 Flash-Lite).
MAX_OUTPUT_TOKENS = 65536


# ---------------------------------------------------------------------------------------------------
# THE REQUEST

def api_url(model, base_url=API_BASE_URL):
    """The generateContent URL of `model`."""
    return base_url + urllib.parse.quote(model.strip(), safe='') + ':generateContent'


def store_result_declaration():
    """The function declaration offered to the model: the Gemini twin of mh_api_call.store_result_tool."""
    return {
        'name': STORE_RESULT_TOOL,
        'description': 'Store the final answer of this task. Call it exactly once, with the complete answer as '
                       'the result argument. Whatever is not passed here is lost.',
        'parameters': {
            'type': 'object',
            'properties': {
                'result': {'type': 'string', 'description': 'The complete answer, exactly as the task asks for it.'},
            },
            'required': ['result'],
        },
    }


def thinking_level(effort):
    """The thinkingLevel of a run's effort, in the API's spelling (upper-case), None for no effort; an effort that is not
    one of the API's levels is refused - RG never seeds one for a Gemini model."""
    if effort is None or not effort.strip():
        return None
    level = effort.strip().upper()
    if level not in THINKING_LEVELS:
        raise ValueError('unknown effort ' + repr(effort) + ' on the gemini_api path - one of ' + str(list(THINKING_LEVELS)))
    return level


def thinking_room(level):
    """The maxOutputTokens room for the thinking of a thinkingLevel, DEFAULT_THINKING_ROOM for None."""
    if level is None:
        return DEFAULT_THINKING_ROOM
    room = THINKING_ROOM.get(level)
    if room is None:
        raise ValueError('unknown thinkingLevel ' + repr(level) + ' - one of ' + str(list(THINKING_LEVELS)))
    return room


def request_body(prompt, max_tokens, level=None):
    """The generateContent request: one user turn with the prompt verbatim, the store tool declared under mode AUTO,
    maxOutputTokens the answer's budget plus thinking_room(level), capped at MAX_OUTPUT_TOKENS, and the thinkingLevel
    when the run names one."""
    if max_tokens < 1:
        raise ValueError('max-tokens must be greater than 0, got ' + str(max_tokens))
    generation_config = {'maxOutputTokens': min(max_tokens + thinking_room(level), MAX_OUTPUT_TOKENS)}
    if level is not None:
        generation_config['thinkingConfig'] = {'thinkingLevel': level}
    return {
        'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
        'tools': [{'functionDeclarations': [store_result_declaration()]}],
        'toolConfig': {'functionCallingConfig': {'mode': 'AUTO'}},
        'generationConfig': generation_config,
    }


# ---------------------------------------------------------------------------------------------------
# THE RESPONSE

def answer_from_response(envelope):
    """The `result` of the one mh_cc_store_result call in a 2xx generateContent response (a parsed dict).

    Fails rather than guessing, as the Anthropic path does:
      - no candidate (a blocked prompt: promptFeedback says why);
      - finishReason MAX_TOKENS: the call was cut at the budget, so the answer is incomplete;
      - no mh_cc_store_result call, or more than one - free text is not an answer;
      - a result that is not a string, or is blank.
    """
    candidates = envelope.get('candidates') if isinstance(envelope, dict) else None
    if not candidates or not isinstance(candidates[0], dict):
        raise ValueError('the response has no candidate; promptFeedback='
                         + json.dumps(envelope.get('promptFeedback') if isinstance(envelope, dict) else None))
    candidate = candidates[0]
    finish_reason = candidate.get('finishReason')
    if finish_reason == 'MAX_TOKENS':
        raise ValueError('the response hit maxOutputTokens - the answer is cut off. Raise meta max-tokens (was '
                         + str((envelope.get('usageMetadata') or {}).get('candidatesTokenCount')) + ' output tokens)')
    content = candidate.get('content')
    parts = content.get('parts') if isinstance(content, dict) else None
    calls = [p['functionCall'] for p in parts or []
             if isinstance(p, dict) and isinstance(p.get('functionCall'), dict)
             and p['functionCall'].get('name') == STORE_RESULT_TOOL]
    if len(calls) != 1:
        kinds = ['/'.join(sorted(p.keys())) if isinstance(p, dict) else type(p).__name__ for p in parts or []]
        raise ValueError('expected exactly one ' + STORE_RESULT_TOOL + ' call, got ' + str(len(calls))
                         + '; finishReason=' + str(finish_reason) + ', parts=' + str(kinds))
    result = (calls[0].get('args') or {}).get('result')
    if not isinstance(result, str):
        raise ValueError(STORE_RESULT_TOOL + ' was called without a string result, got ' + type(result).__name__)
    if not result.strip():
        raise ValueError(STORE_RESULT_TOOL + ' was called with an empty result - there is nothing to store')
    return result


def api_failure_line(status, body):
    """The console line for a non-2xx response. The analyzers in mh-function.yaml match its wording - keep it."""
    snippet = '<no body>' if body is None else (body[:MAX_BODY_SNIPPET] + '...' if len(body) > MAX_BODY_SNIPPET else body)
    return 'Gemini API call failed with status ' + str(status) + '; body=' + snippet


def api_error_message(text):
    """The API's own error message of a failed response (its error.message), else the body's first MAX_BODY_SNIPPET chars."""
    try:
        message = ((json.loads(text) or {}).get('error') or {}).get('message')
    except (ValueError, TypeError, AttributeError):
        message = None
    if message:
        return str(message)
    return '<no body>' if not text else text[:MAX_BODY_SNIPPET]


# ---------------------------------------------------------------------------------------------------
# THE BOUNDARY

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # a 3xx is a failed call, not a new request - the key header must never follow a redirect
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_generate_content(url, api_key, body, timeout_sec):
    """One POST of `body` (a dict) to generateContent: (status, response text). Non-2xx is returned, not raised."""
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(url, data=data, method='POST', headers={
        'content-type': 'application/json',
        'x-goog-api-key': api_key,
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
