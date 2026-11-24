# Unit tests for the gemini_api path of mh.asset.call-cc: mh_gemini_call's pure core, its boundary call, mh_metrics'
# Gemini counts, and mh_call_cc.run_gemini_api end to end inside a tmp task dir.
#
# Two stand-ins, each behaving one way for every test:
#   - ProcessorSecretChannel (test_mh_api_call): the Processor's side of the loopback secret protocol.
#   - EchoGeminiApi: a local generateContent. A request without the key it was built with gets 400 INVALID_ARGUMENT
#     with reason API_KEY_INVALID, as Google answers an invalid key; any other request gets one mh_cc_store_result
#     function call whose result is the user turn's text, in the shape the live API gave on 2026-11-23.
# The assertions are on what production built (the request) and produced (the output Variable file, the exit code).
#
# Run:  pytest call-cc/tests

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import mh_call_cc
import mh_gemini_call
import mh_metrics
from mh_gemini_call import (STORE_RESULT_TOOL, answer_from_response, api_failure_line, api_url, request_body,
                            thinking_level, thinking_room)
from test_mh_api_call import ProcessorSecretChannel


class EchoGeminiApi:
    def __init__(self, key):
        self.requests = []
        recorder = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])).decode('utf-8'))
                recorder.requests.append({'path': self.path, 'headers': {k.lower(): v for k, v in self.headers.items()},
                                          'body': body})
                if self.headers.get('x-goog-api-key') != key:
                    status, payload = 400, {'error': {'code': 400, 'message': 'API key not valid. Please pass a valid API key.',
                                                      'status': 'INVALID_ARGUMENT',
                                                      'details': [{'reason': 'API_KEY_INVALID'}]}}
                else:
                    text = body['contents'][0]['parts'][0]['text']
                    status, payload = 200, {
                        'candidates': [{'content': {'parts': [{'functionCall': {'name': STORE_RESULT_TOOL,
                                                                                'args': {'result': text},
                                                                                'id': 'call_1'},
                                                               'thoughtSignature': 'EpYB'}],
                                                    'role': 'model'},
                                        'finishReason': 'STOP', 'index': 0,
                                        'finishMessage': 'Model generated function call(s).'}],
                        'usageMetadata': {'promptTokenCount': 106, 'candidatesTokenCount': 28, 'totalTokenCount': 134},
                        'modelVersion': 'gemini-3.5-flash-lite'}
                data = json.dumps(payload, indent=2).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=UTF-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(('127.0.0.1', 0), Handler)
        self.base_url = 'http://127.0.0.1:' + str(self.httpd.server_address[1]) + '/v1beta/models/'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _response(parts, finish_reason='STOP'):
    return {'candidates': [{'content': {'parts': parts, 'role': 'model'}, 'finishReason': finish_reason}]}


def _store(result):
    return {'functionCall': {'name': STORE_RESULT_TOOL, 'args': {'result': result}, 'id': 'c'}}


# ----------------------------------------------------------------- the request

def test_request_body_declares_the_store_tool_under_auto_and_sends_the_prompt_verbatim():
    body = request_body('the prompt — ü', 200, 'HIGH')
    assert body['contents'] == [{'role': 'user', 'parts': [{'text': 'the prompt — ü'}]}]
    [declaration] = body['tools'][0]['functionDeclarations']
    assert declaration['name'] == STORE_RESULT_TOOL
    assert declaration['parameters'] == {'type': 'object', 'required': ['result'], 'properties': {
        'result': {'type': 'string', 'description': 'The complete answer, exactly as the task asks for it.'}}}
    assert body['toolConfig'] == {'functionCallingConfig': {'mode': 'AUTO'}}
    assert body['generationConfig'] == {'maxOutputTokens': 200 + 32768, 'thinkingConfig': {'thinkingLevel': 'HIGH'}}


def test_request_body_without_an_effort_sends_no_thinking_config():
    assert request_body('p', 100)['generationConfig'] == {'maxOutputTokens': 100 + 2048}


def test_request_body_caps_max_output_tokens_and_refuses_a_bad_budget():
    assert request_body('p', 60000, 'HIGH')['generationConfig']['maxOutputTokens'] == 65536
    with pytest.raises(ValueError, match='max-tokens must be greater than 0'):
        request_body('p', 0)


@pytest.mark.parametrize('effort,level', [('MINIMAL', 'MINIMAL'), ('low', 'LOW'), (' Medium ', 'MEDIUM'),
                                          ('HIGH', 'HIGH'), (None, None), ('  ', None)])
def test_thinking_level_of_an_effort(effort, level):
    assert thinking_level(effort) == level


@pytest.mark.parametrize('effort', ['extra', 'max', 'xhigh'])
def test_an_effort_the_api_does_not_know_is_refused(effort):
    with pytest.raises(ValueError, match='on the gemini_api path'):
        thinking_level(effort)


def test_thinking_room_per_level():
    assert [thinking_room(level) for level in ('MINIMAL', 'LOW', 'MEDIUM', 'HIGH', None)] == [2048, 8192, 16384, 32768, 2048]
    with pytest.raises(ValueError):
        thinking_room('max')


def test_api_url_of_a_model():
    assert api_url(' gemini-3.5-flash-lite ') == ('https://generativelanguage.googleapis.com/v1beta/models/'
                                                  'gemini-3.5-flash-lite:generateContent')


# ----------------------------------------------------------------- the response

def test_the_answer_is_the_one_store_calls_result_verbatim_never_the_free_text():
    response = _response([{'text': 'Here you go:'}, dict(_store('["red", "blue", "yellow"]'), thoughtSignature='s')])
    assert answer_from_response(response) == '["red", "blue", "yellow"]'


def test_an_answer_cut_at_max_tokens_is_refused():
    with pytest.raises(ValueError, match='hit maxOutputTokens'):
        answer_from_response(_response([_store('[1, 2')], 'MAX_TOKENS'))


@pytest.mark.parametrize('parts', [[], [{'text': 'free text only'}], [_store('a'), _store('b')],
                                   [{'functionCall': {'name': 'other_tool', 'args': {'result': 'x'}}}]])
def test_anything_but_exactly_one_store_call_is_refused(parts):
    with pytest.raises(ValueError, match='expected exactly one ' + STORE_RESULT_TOOL + ' call'):
        answer_from_response(_response(parts))


@pytest.mark.parametrize('result,message', [(None, 'without a string result'), (7, 'without a string result'),
                                            ('  ', 'empty result')])
def test_an_empty_or_non_string_result_is_refused(result, message):
    with pytest.raises(ValueError, match=message):
        answer_from_response(_response([_store(result)]))


def test_a_response_without_a_candidate_names_the_prompt_feedback():
    with pytest.raises(ValueError, match='no candidate; promptFeedback=\\{"blockReason": "SAFETY"\\}'):
        answer_from_response({'promptFeedback': {'blockReason': 'SAFETY'}})


def test_the_failure_line_carries_the_wording_the_analyzers_match():
    assert api_failure_line(429, '{"error": {"status": "RESOURCE_EXHAUSTED"}}') == (
        'Gemini API call failed with status 429; body={"error": {"status": "RESOURCE_EXHAUSTED"}}')
    assert api_failure_line(500, None) == 'Gemini API call failed with status 500; body=<no body>'


# ----------------------------------------------------------------- metrics

def test_gemini_counts_of_the_live_usage():
    text = json.dumps({'usageMetadata': {'promptTokenCount': 106, 'candidatesTokenCount': 28, 'totalTokenCount': 134}})
    assert mh_metrics.gemini_counts(200, text) == {'inputTokens': 106, 'outputTokens': 28,
                                                   'cacheCreationInputTokens': None, 'cacheReadInputTokens': None}
    assert mh_metrics.gemini_counts(404, text) == mh_metrics.no_tokens()


def test_gemini_tokens_count_thinking_as_output_and_cache_as_read():
    assert mh_metrics.gemini_tokens({'promptTokenCount': 100, 'cachedContentTokenCount': 60, 'candidatesTokenCount': 20,
                                     'thoughtsTokenCount': 30}) == {
        'inputTokens': 40, 'outputTokens': 50, 'cacheCreationInputTokens': None, 'cacheReadInputTokens': 60}


# ----------------------------------------------------------------- llm_provider

def test_llm_provider_knows_gemini_api():
    assert mh_call_cc.llm_provider([{'llm_provider': ' gemini_api '}]) == 'gemini_api'
    with pytest.raises(ValueError, match="'llm_provider' must be 'cc', 'claude_api' or 'gemini_api', got 'gemini'"):
        mh_call_cc.llm_provider([{'llm_provider': 'gemini'}])


# ----------------------------------------------------------------- run_gemini_api, end to end in a task dir

def _task(tmp_path, channel=None, metrics=False):
    outputs = [{'id': '9', 'name': 'ccResult'}]
    if metrics:
        outputs.append({'id': '11', 'name': 'callMetrics', 'type': 'mh.metrics'})
    params = {'workingPath': str(tmp_path), 'outputs': outputs}
    if channel is not None:
        params.update({'secretPort': channel.port, 'checkCode': channel.check_code})
    return params


def test_run_gemini_api_stores_the_store_calls_result_verbatim(tmp_path):
    api = EchoGeminiApi('gem-test')
    channel = ProcessorSecretChannel('gm-1', b'gem-test')
    params = _task(tmp_path, channel, metrics=True)
    try:
        code = mh_call_cc.run_gemini_api(params, [{'max-tokens': '200'}, {'timeout-sec': '30'}], str(tmp_path),
                                         'answer with\ntwo lines', params['outputs'][0], 'gemini-3.5-flash-lite', 'LOW',
                                         api_base_url=api.base_url, metrics_var=params['outputs'][1])
    finally:
        api.close()

    assert code == 0
    assert (tmp_path / 'artifacts' / '9').read_bytes() == b'answer with\ntwo lines'
    [request] = api.requests
    assert request['path'] == '/v1beta/models/gemini-3.5-flash-lite:generateContent'
    assert request['headers']['x-goog-api-key'] == 'gem-test'
    assert request['body']['generationConfig'] == {'maxOutputTokens': 200 + 8192, 'thinkingConfig': {'thinkingLevel': 'LOW'}}
    assert request['body']['toolConfig'] == {'functionCallingConfig': {'mode': 'AUTO'}}
    response_file = (tmp_path / 'cc-data' / 'api-response.json').read_text(encoding='utf-8')
    assert json.loads(response_file)['candidates'][0]['finishReason'] == 'STOP'
    assert 'gem-test' not in response_file
    [call] = json.loads((tmp_path / 'artifacts' / '11').read_text(encoding='utf-8'))
    assert (call['type'], call['inputTokens'], call['outputTokens']) == ('API', 106, 28)


def test_run_gemini_api_with_a_rejected_key_fails_with_the_analyzer_line(tmp_path, capsys):
    api = EchoGeminiApi('gem-real')
    channel = ProcessorSecretChannel('gm-2', b'gem-revoked')
    params = _task(tmp_path, channel)
    try:
        code = mh_call_cc.run_gemini_api(params, [], str(tmp_path), 'p', params['outputs'][0], 'gemini-3.5-flash-lite',
                                         None, api_base_url=api.base_url)
    finally:
        api.close()

    assert code == 1
    console = capsys.readouterr().out
    assert 'FAILED: Gemini API call failed with status 400; body=' in console
    assert 'API_KEY_INVALID' in console
    assert 'the API: API key not valid. Please pass a valid API key.' in console
    assert 'gem-revoked' not in console
    assert not (tmp_path / 'artifacts' / '9').exists()


def test_run_gemini_api_refuses_a_claude_effort_before_any_call(tmp_path, capsys):
    params = _task(tmp_path, ProcessorSecretChannel('gm-3', b'k'))
    assert mh_call_cc.run_gemini_api(params, [], str(tmp_path), 'p', params['outputs'][0], 'gemini-3.5-flash-lite',
                                     'extra') == 1
    assert "FAILED: unknown effort 'extra' on the gemini_api path" in capsys.readouterr().out


def test_run_gemini_api_without_a_handoff_or_a_model_fails_before_any_call(tmp_path, capsys):
    params = _task(tmp_path)
    assert mh_call_cc.run_gemini_api(params, [], str(tmp_path), 'p', params['outputs'][0], 'm', None) == 1
    assert 'no API key was handed over' in capsys.readouterr().out
    assert mh_call_cc.run_gemini_api(params, [], str(tmp_path), 'p', params['outputs'][0], None, None) == 1
    assert 'no model for llm_provider=gemini_api' in capsys.readouterr().out
