# mh_metrics - the execution time and token usage of every model call a Function makes, written into the one output
# Variable of type mh.metrics when the process declares one.
#
# The Function SEARCHES its outputs for that type; nothing names it by a meta. A process opts in by declaring
#
#     -> <any name>: type=mh.metrics, ext=".json"
#
# and a process that declares none gets no file and runs exactly as before. Two such outputs on one process are a
# SourceCode defect (metrics_output raises before any paid call).
#
# The content is a JSON list - one entry per call of CC or of the API, in call order:
#
#     [{"type": "CC", "executionMs": 6810, "inputTokens": 2, "outputTokens": 193,
#       "cacheCreationInputTokens": 18176, "cacheReadInputTokens": 16560}]
#
#   type                      "CC": one Claude Code CLI session; "API": one Anthropic Messages API request
#   executionMs               the wall time of that one call - the CC process, the HTTP request - never the Function's
#   inputTokens, outputTokens as the call reported them
#   cacheCreationInputTokens, cacheReadInputTokens
#                             the cached part of the input. With prompt caching inputTokens is only the uncached
#                             remainder: a CC call measured on 2026-11-06 reported 2 input tokens and 34736 written to
#                             or read from the cache
#   any count                 null when the call reported none: a failed request, a CC console without a result line
#
# A CC session reports its counts in the one JSON line `--output-format json` prints (`"type": "result"`, measured on
# CC 2.1.314, 2026-11-06): summed here over its `modelUsage` - every model the session used, a subagent's included -
# else read from its `usage`. An API response reports them in `usage`.
#
# Everything here is pure except write_metrics; metered takes the post and the clock as parameters.

import json
import time

METRICS_TYPE = 'mh.metrics'

CALL_CC = 'CC'
CALL_API = 'API'

# (the record's name, the API's usage key) - modelUsage, per model, uses the record's names
TOKEN_FIELDS = (('inputTokens', 'input_tokens'),
                ('outputTokens', 'output_tokens'),
                ('cacheCreationInputTokens', 'cache_creation_input_tokens'),
                ('cacheReadInputTokens', 'cache_read_input_tokens'))


def metrics_output(outputs):
    """The one output Variable of type mh.metrics among the task's outputs, or None when there is none. A ValueError
    for two or more: which of them would hold the record is not this Function's guess to make."""
    found = [v for v in outputs or [] if isinstance(v, dict) and v.get('type') == METRICS_TYPE]
    if len(found) > 1:
        raise ValueError('more than one output variable of type ' + METRICS_TYPE + ' is declared: '
                         + str([v.get('name') for v in found]) + ' - a process declares at most one')
    return found[0] if found else None


def _count(value):
    # a token count is an int; JSON's true/false are not counts, though Python's bool is an int
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def no_tokens():
    """The four counts of a call that reported none."""
    return {name: None for name, _ in TOKEN_FIELDS}


def api_tokens(usage):
    """The four counts of an API `usage` object (snake_case keys); None for each one it does not carry."""
    usage = usage if isinstance(usage, dict) else {}
    return {name: _count(usage.get(key)) for name, key in TOKEN_FIELDS}


def cc_result(console):
    """The CC CLI's result object - the LAST console line that is a JSON object with "type": "result" - or None.
    None is not an error: the CLI may have failed before it could print the line."""
    for line in reversed((console or '').splitlines()):
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get('type') == 'result':
            return value
    return None


def cc_result_text(result):
    """The session's final text - the "result" of the result object - or None."""
    text = result.get('result') if isinstance(result, dict) else None
    return text if isinstance(text, str) else None


def cc_tokens(result):
    """The four counts of a CC session: each summed over the result's `modelUsage`, else read from its `usage`;
    None for a count that no model reported."""
    if not isinstance(result, dict):
        return no_tokens()
    by_model = result.get('modelUsage')
    if isinstance(by_model, dict) and by_model:
        totals = {}
        for name, _ in TOKEN_FIELDS:
            counts = [_count(m.get(name)) for m in by_model.values() if isinstance(m, dict)]
            counts = [c for c in counts if c is not None]
            totals[name] = sum(counts) if counts else None
        return totals
    return api_tokens(result.get('usage'))


def call(call_type, execution_ms, tokens):
    """One entry of the list."""
    return dict({'type': call_type, 'executionMs': execution_ms}, **tokens)


def elapsed_ms(started, now=time.monotonic):
    """Whole milliseconds since `started`, a value of `now`."""
    return int(round((now() - started) * 1000))


def response_usage(status, text):
    """The `usage` of a 2xx API response text, or None (another status, no text, not JSON)."""
    if status is None or status < 200 or status >= 300 or not text:
        return None
    try:
        envelope = json.loads(text)
    except ValueError:
        return None
    return envelope.get('usage') if isinstance(envelope, dict) else None


def metered(post, calls, now=time.monotonic):
    """post(body, seconds) -> (status, text), unchanged, recording one API entry into `calls` per request: its time,
    and the counts of a 2xx response. A request that raises is recorded too, with no counts."""
    def metered_post(body, seconds):
        started = now()
        status, text = None, None
        try:
            status, text = post(body, seconds)
            return status, text
        finally:
            calls.append(call(CALL_API, elapsed_ms(started, now), api_tokens(response_usage(status, text))))
    return metered_post


def metrics_json(calls):
    """The file's content: the list, as JSON."""
    return json.dumps(list(calls), indent=2) + '\n'


def write_metrics(path, calls):
    """The list into the output Variable's file. LF line ends on every OS."""
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(metrics_json(calls))
