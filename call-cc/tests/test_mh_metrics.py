# mh_metrics - the mh.metrics output: which Variable, what one call records, how a CC result line and an API
# response become counts. Pure functions only; the Function's use of them is covered by
# test_mh_call_cc_metrics_integration.py.
#
# Run:  pytest call-cc/tests

import json

import pytest

import mh_metrics
from mh_metrics import (metrics_output, api_tokens, cc_result, cc_result_text, cc_tokens, call, elapsed_ms,
                        response_usage, metered, metrics_json, write_metrics, no_tokens)

# The result line of a real CC 2.1.314 run (`claude --debug --print --output-format json --model haiku`, 2026-11-06),
# cut to the fields this module reads - the counts are the measured ones.
CC_RESULT_LINE = json.dumps({
    'type': 'result', 'subtype': 'success', 'is_error': False, 'duration_ms': 2096, 'result': 'OK',
    'usage': {'input_tokens': 2, 'cache_creation_input_tokens': 18176, 'cache_read_input_tokens': 16560,
              'output_tokens': 193, 'output_tokens_details': {'thinking_tokens': 189}},
    'modelUsage': {'claude-haiku-5-5': {'inputTokens': 2, 'outputTokens': 193, 'cacheReadInputTokens': 16560,
                                        'cacheCreationInputTokens': 18176, 'thinkingTokens': 189}},
})

MEASURED = {'inputTokens': 2, 'outputTokens': 193, 'cacheCreationInputTokens': 18176, 'cacheReadInputTokens': 16560}


# ----------------------------------------------------------------- which output receives the record

def test_metrics_output_finds_the_output_of_type_mh_metrics_whatever_its_name():
    outputs = [{'name': 'cvNeedResult', 'id': '7'}, {'name': 'ccMetrics', 'id': '8', 'type': 'mh.metrics'}]

    assert metrics_output(outputs)['id'] == '8'


def test_metrics_output_is_none_when_the_process_declares_none():
    for outputs in [None, [], [{'name': 'result', 'id': '1'}], [{'name': 'r', 'id': '1', 'type': 'requirement'}]]:
        assert metrics_output(outputs) is None, repr(outputs)


def test_metrics_output_refuses_two_and_names_both():
    outputs = [{'name': 'a', 'id': '1', 'type': 'mh.metrics'}, {'name': 'b', 'id': '2', 'type': 'mh.metrics'}]

    with pytest.raises(ValueError) as e:
        metrics_output(outputs)
    assert "['a', 'b']" in str(e.value)


def test_metrics_output_matches_the_type_exactly():
    # a prefix or a near miss is another type, not this one
    for t in ['mh.metrics.v2', 'MH.METRICS', 'metrics', ' mh.metrics']:
        assert metrics_output([{'name': 'm', 'id': '1', 'type': t}]) is None, t


# ----------------------------------------------------------------- the API's usage

def test_api_tokens_reads_the_four_snake_case_counts():
    usage = {'input_tokens': 10, 'output_tokens': 20, 'cache_creation_input_tokens': 30, 'cache_read_input_tokens': 40}

    assert api_tokens(usage) == {'inputTokens': 10, 'outputTokens': 20, 'cacheCreationInputTokens': 30,
                                 'cacheReadInputTokens': 40}


def test_api_tokens_leaves_a_count_null_when_the_usage_lacks_it():
    assert api_tokens({'input_tokens': 10, 'output_tokens': 20}) == {
        'inputTokens': 10, 'outputTokens': 20, 'cacheCreationInputTokens': None, 'cacheReadInputTokens': None}


def test_api_tokens_of_no_usage_is_all_null():
    for usage in [None, {}, 'not a dict', []]:
        assert api_tokens(usage) == no_tokens(), repr(usage)


def test_api_tokens_takes_only_integers_as_counts():
    # JSON true is a Python bool, and a bool is an int - it must still not pass for a count
    assert api_tokens({'input_tokens': True, 'output_tokens': '5', 'cache_read_input_tokens': 1.5}) == no_tokens()


# ----------------------------------------------------------------- the CC result line

def test_cc_result_finds_the_one_line_output_format_json_prints():
    assert cc_result(CC_RESULT_LINE + '\n')['result'] == 'OK'


def test_cc_result_skips_debug_lines_and_takes_the_last_result():
    first = json.dumps({'type': 'result', 'result': 'first'})
    last = json.dumps({'type': 'result', 'result': 'last'})
    console = '[DEBUG] starting\n' + first + '\n{not json\n' + last + '\n[DEBUG] done\r\n'

    assert cc_result(console)['result'] == 'last'


def test_cc_result_ignores_json_lines_that_are_not_the_result():
    console = json.dumps({'type': 'system', 'subtype': 'init'}) + '\n' + json.dumps([1, 2]) + '\n'

    assert cc_result(console) is None


def test_cc_result_is_none_for_a_text_console():
    # a CLI that failed before printing its result line, or a console of --output-format text
    for console in [None, '', 'error: unknown option --effort\n', 'MCP_UNAVAILABLE: CONNECTION_CLOSED\n']:
        assert cc_result(console) is None, repr(console)


def test_cc_result_text_is_the_sessions_final_text():
    assert cc_result_text(cc_result(CC_RESULT_LINE)) == 'OK'


def test_cc_result_text_is_none_without_a_result_or_a_string():
    for result in [None, {}, {'type': 'result'}, {'type': 'result', 'result': 42}]:
        assert cc_result_text(result) is None, repr(result)


def test_cc_tokens_of_the_measured_line():
    assert cc_tokens(cc_result(CC_RESULT_LINE)) == MEASURED


def test_cc_tokens_sums_every_model_the_session_used():
    # a session that started a subagent on another model reports both under modelUsage
    result = {'type': 'result', 'usage': {'input_tokens': 1, 'output_tokens': 1},
              'modelUsage': {'claude-opus-5-5': {'inputTokens': 5, 'outputTokens': 100, 'cacheReadInputTokens': 1000,
                                                 'cacheCreationInputTokens': 10},
                             'claude-haiku-5-5': {'inputTokens': 3, 'outputTokens': 7}}}

    assert cc_tokens(result) == {'inputTokens': 8, 'outputTokens': 107, 'cacheCreationInputTokens': 10,
                                 'cacheReadInputTokens': 1000}


def test_cc_tokens_falls_back_to_usage_without_model_usage():
    result = {'type': 'result', 'usage': {'input_tokens': 2, 'output_tokens': 193,
                                          'cache_creation_input_tokens': 18176, 'cache_read_input_tokens': 16560}}

    assert cc_tokens(result) == MEASURED


def test_cc_tokens_of_no_result_is_all_null():
    assert cc_tokens(None) == no_tokens()


# ----------------------------------------------------------------- one entry, and its time

def test_call_puts_the_type_and_the_time_first_then_the_counts():
    entry = call(mh_metrics.CALL_CC, 6810, MEASURED)

    assert entry == dict({'type': 'CC', 'executionMs': 6810}, **MEASURED)
    assert list(entry)[:2] == ['type', 'executionMs']


def test_elapsed_ms_is_whole_milliseconds_of_the_clock_given():
    assert elapsed_ms(10.0, now=lambda: 12.3456) == 2346


# ----------------------------------------------------------------- API requests, metered one by one

def _envelope(status, usage):
    return status, json.dumps({'content': [], 'usage': usage})


def test_response_usage_is_the_usage_of_a_2xx_response():
    assert response_usage(*_envelope(200, {'input_tokens': 4})) == {'input_tokens': 4}


def test_response_usage_is_none_for_a_failure_or_garbage():
    for status, text in [(429, '{"usage": {"input_tokens": 4}}'), (200, ''), (200, None), (200, 'not json'),
                         (200, '[1]'), (None, None)]:
        assert response_usage(status, text) is None, repr((status, text))


def test_metered_records_every_request_with_its_own_time_and_counts():
    clock = iter([0.0, 1.5, 10.0, 10.25])
    answers = iter([_envelope(200, {'input_tokens': 4, 'output_tokens': 5}), (529, '{"type": "error"}')])
    calls = []
    post = metered(lambda body, seconds: next(answers), calls, now=lambda: next(clock))

    assert post({'model': 'm'}, 60)[0] == 200
    assert post({'model': 'm'}, 60)[0] == 529

    assert calls == [
        {'type': 'API', 'executionMs': 1500, 'inputTokens': 4, 'outputTokens': 5, 'cacheCreationInputTokens': None,
         'cacheReadInputTokens': None},
        dict({'type': 'API', 'executionMs': 250}, **no_tokens()),
    ]


def test_metered_returns_exactly_what_the_post_returned_and_passes_its_arguments():
    seen = []
    answer = _envelope(200, {'input_tokens': 1})

    def post(body, seconds):
        seen.append((body, seconds))
        return answer

    assert metered(post, [])({'k': 'v'}, 42) == answer
    assert seen == [({'k': 'v'}, 42)]


def test_metered_records_a_request_that_raised_and_lets_the_error_through():
    calls = []

    def post(body, seconds):
        raise OSError('connection reset')

    with pytest.raises(OSError):
        metered(post, calls, now=iter([0.0, 2.0]).__next__)({}, 1)
    assert calls == [dict({'type': 'API', 'executionMs': 2000}, **no_tokens())]


# ----------------------------------------------------------------- the file

def test_metrics_json_is_a_json_list_in_call_order():
    calls = [call('CC', 1, MEASURED), call('API', 2, no_tokens())]

    assert json.loads(metrics_json(calls)) == calls


def test_metrics_json_of_no_call_is_an_empty_list():
    assert json.loads(metrics_json([])) == []


def test_write_metrics_writes_lf_utf8_json(tmp_path):
    target = tmp_path / '8'

    write_metrics(str(target), [call('CC', 1, MEASURED)])

    raw = target.read_bytes()
    assert b'\r\n' not in raw
    assert json.loads(raw.decode('utf-8')) == [call('CC', 1, MEASURED)]
