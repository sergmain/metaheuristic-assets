# Unit tests for the claude_api path of mh.asset.call-cc: mh_api_call's pure core, its two boundary calls, and
# mh_call_cc.run_claude_api end to end inside a tmp task dir.
#
# Two stand-ins, each behaving one way for every test:
#   - ProcessorSecretChannel: the Processor's side of the loopback secret protocol - one connection, the framed check
#     code in, the framed key out only when the code matches.
#   - EchoMessagesApi: a local Messages API. A request without the key it was built with gets 401 authentication_error,
#     as the real API answers; any other request gets the forced mh_cc_store_result call with the user turn as `result`.
# The assertions are on what production built (the request) and produced (the output Variable file, the exit code).
#
# Run:  pytest call-cc/tests

import json
import socket
import struct
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import mh_api_call
import mh_call_cc
from mh_api_call import (STORE_RESULT_TOOL, DEFAULT_MAX_TOKENS, request_body, max_tokens, answer_from_response,
                         api_failure_line, read_secret, zero)


def _recv_exact(conn, n):
    buf = b''
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


class ProcessorSecretChannel:
    def __init__(self, check_code, key):
        self.check_code, self.key = check_code, key
        self.server = socket.socket()
        self.server.bind(('127.0.0.1', 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        conn, _ = self.server.accept()
        with conn:
            (n,) = struct.unpack('>i', _recv_exact(conn, 4))
            if _recv_exact(conn, n).decode('utf-8') == self.check_code:
                conn.sendall(struct.pack('>i', len(self.key)) + self.key)
        self.server.close()


class EchoMessagesApi:
    def __init__(self, valid_key):
        self.requests = []
        api = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])).decode('utf-8'))
                headers = {k.lower(): v for k, v in self.headers.items()}
                api.requests.append({'path': self.path, 'headers': headers, 'body': body})
                if headers.get('x-api-key') != valid_key:
                    self._send(401, {'type': 'error', 'error': {'type': 'authentication_error', 'message': 'invalid x-api-key'}})
                    return
                self._send(200, {'id': 'msg_1', 'type': 'message', 'role': 'assistant', 'model': body['model'],
                                 'stop_reason': 'tool_use', 'usage': {'input_tokens': 10, 'output_tokens': 5},
                                 'content': [{'type': 'tool_use', 'id': 'tu_1', 'name': STORE_RESULT_TOOL,
                                              'input': {'result': body['messages'][0]['content']}}]})

            def _send(self, status, payload):
                data = json.dumps(payload).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(('127.0.0.1', 0), Handler)
        self.url = 'http://127.0.0.1:' + str(self.httpd.server_address[1]) + '/v1/messages'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class ForcedToolRefusingApi:
    """A local Messages API that behaves like a model refusing forced tool use (observed 2026-10-25 for
    claude-sonnet-5-5, plan 050 Phase 17): tool_choice type tool or any -> 400 invalid_request_error with the API's own
    message; any other request -> the mh_cc_store_result call with the user turn as `result`. One behaviour for every test."""

    REFUSAL = 'tool_choice: type "tool" and "any" are not supported for this model.'

    def __init__(self):
        self.requests = []
        api = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])).decode('utf-8'))
                api.requests.append({'path': self.path, 'body': body})
                if (body.get('tool_choice') or {}).get('type') in ('tool', 'any'):
                    self._send(400, {'type': 'error', 'error': {'type': 'invalid_request_error',
                                                                 'message': ForcedToolRefusingApi.REFUSAL}})
                    return
                self._send(200, {'id': 'msg_2', 'type': 'message', 'role': 'assistant', 'model': body['model'],
                                 'stop_reason': 'tool_use', 'usage': {'input_tokens': 11, 'output_tokens': 6},
                                 'content': [{'type': 'text', 'text': 'storing the answer'},
                                             {'type': 'tool_use', 'id': 'tu_2', 'name': STORE_RESULT_TOOL,
                                              'input': {'result': body['messages'][0]['content']}}]})

            def _send(self, status, payload):
                data = json.dumps(payload).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(('127.0.0.1', 0), Handler)
        self.url = 'http://127.0.0.1:' + str(self.httpd.server_address[1]) + '/v1/messages'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class Haiku55Api:
    """A local Messages API that behaves as Claude Haiku 5.5 does by the API's thinking documentation (per-model table,
    2026-10-25) and by run #106 of plan 050 Phase 17 (Task #202108: 'refuses extended thinking', then thinking_tokens 0):
    thinking type enabled (a budget_tokens request) -> 400 invalid_request_error naming thinking; any other request -> 200
    with the mh_cc_store_result call (the user turn as `result`) - under a forced tool_choice the call alone (a forced tool
    starts the response with the call, no thinking block), otherwise a thinking block before the call, as adaptive
    thinking - the model's default - returns it (display omitted: an empty thinking text). One behaviour for every test.
    The refusal's wording is this stand-in's own: #106 ran before the payload printed the API's message."""

    REFUSAL = 'thinking.type: "enabled" is not supported for this model. Use "adaptive" instead.'

    def __init__(self):
        self.requests = []
        api = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])).decode('utf-8'))
                api.requests.append({'path': self.path, 'body': body})
                if (body.get('thinking') or {}).get('type') == 'enabled':
                    self._send(400, {'type': 'error', 'error': {'type': 'invalid_request_error',
                                                                 'message': Haiku55Api.REFUSAL}})
                    return
                call = {'type': 'tool_use', 'id': 'tu_3', 'name': STORE_RESULT_TOOL,
                        'input': {'result': body['messages'][0]['content']}}
                forced = (body.get('tool_choice') or {}).get('type') in ('tool', 'any')
                content = [call] if forced else [{'type': 'thinking', 'thinking': '', 'signature': 'sig'}, call]
                self._send(200, {'id': 'msg_3', 'type': 'message', 'role': 'assistant', 'model': body['model'],
                                 'stop_reason': 'tool_use', 'content': content,
                                 'usage': {'input_tokens': 12, 'output_tokens': 7 if forced else 47,
                                           'output_tokens_details': {'thinking_tokens': 0 if forced else 40}}})

            def _send(self, status, payload):
                data = json.dumps(payload).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(('127.0.0.1', 0), Handler)
        self.url = 'http://127.0.0.1:' + str(self.httpd.server_address[1]) + '/v1/messages'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _envelope(content, stop_reason='tool_use'):
    return {'content': content, 'stop_reason': stop_reason, 'usage': {'output_tokens': 7}}


def _store(result):
    return {'type': 'tool_use', 'id': 'tu', 'name': STORE_RESULT_TOOL, 'input': {'result': result}}


# ----------------------------------------------------------------- the request

def test_request_body_sends_the_prompt_verbatim_and_offers_the_store_tool_under_auto():
    # plan 050 Phase 17 (rewritten 2026-10-25, section 9.3 rule 2 - was ..._and_forces_the_store_tool: the forced tool,
    # max_tokens 100): the tool under tool_choice auto, no thinking field, no effort sent, the default thinking room
    body = request_body(' claude-haiku-5-5 ', 'line 1\nline 2 \u2014 \u00fc', 100)

    assert body['model'] == 'claude-haiku-5-5'
    assert body['max_tokens'] == 100 + 32768
    assert body['messages'] == [{'role': 'user', 'content': 'line 1\nline 2 \u2014 \u00fc'}]
    assert [t['name'] for t in body['tools']] == [STORE_RESULT_TOOL]
    assert body['tools'][0]['input_schema']['required'] == ['result']
    assert body['tool_choice'] == {'type': 'auto'}
    assert 'thinking' not in body
    assert 'output_config' not in body


def test_request_body_offers_the_store_tool_under_auto_to_every_model():
    # plan 050 Phase 17: the second request to a model that refuses forced tool use
    # (rewritten 2026-10-25, section 9.3 rule 2 - was ..._not_forced_...: forced=False is gone; every request is this one)
    body = request_body('claude-sonnet-5-5', 'p', 100)
    assert body['tool_choice'] == {'type': 'auto'}
    assert body['tools'] == [mh_api_call.store_result_tool()]
    assert body['messages'] == [{'role': 'user', 'content': 'p'}]


def test_tool_choice_refused_is_the_apis_400_naming_tool_choice_only():
    refusal = json.dumps({'type': 'error', 'error': {'type': 'invalid_request_error',
                                                     'message': ForcedToolRefusingApi.REFUSAL}})
    assert mh_api_call.tool_choice_refused(400, refusal)
    assert not mh_api_call.tool_choice_refused(401, refusal), 'not the status the API refuses a request shape with'
    assert not mh_api_call.tool_choice_refused(400, json.dumps({'type': 'error', 'error': {
        'type': 'invalid_request_error', 'message': 'max_tokens: must be at least 1'}})), 'another invalid request'
    assert not mh_api_call.tool_choice_refused(400, 'not json at all naming tool_choice'), 'only the API error body'
    assert not mh_api_call.tool_choice_refused(400, None)


def test_request_body_refuses_a_missing_model_and_a_bad_budget():
    with pytest.raises(ValueError, match='a model is required'):
        request_body('  ', 'p', 100)
    with pytest.raises(ValueError, match='max-tokens'):
        request_body('m', 'p', 0)


def test_max_tokens_from_the_meta_value():
    assert max_tokens(None) == DEFAULT_MAX_TOKENS
    assert max_tokens('  ') == DEFAULT_MAX_TOKENS
    assert max_tokens(' 32000 ') == 32000
    with pytest.raises(ValueError, match='greater than 0'):
        max_tokens('0')


# ----------------------------------------------------------------- the response

def test_the_answer_is_the_one_store_calls_result_verbatim_never_the_free_text():
    envelope = _envelope([{'type': 'text', 'text': 'Here is my answer:'}, _store('{"a": 1}\n{"b": 2}\n')])

    assert answer_from_response(envelope) == '{"a": 1}\n{"b": 2}\n'


def test_an_answer_cut_at_max_tokens_is_refused():
    envelope = _envelope([_store('{"a": 1}\n{"b"')], stop_reason='max_tokens')

    with pytest.raises(ValueError, match='hit max_tokens'):
        answer_from_response(envelope)


@pytest.mark.parametrize('content', [
    [],
    [{'type': 'text', 'text': 'the answer, printed instead of stored'}],
    [_store('one'), _store('two')],
    [{'type': 'tool_use', 'name': 'some_other_tool', 'input': {'result': 'x'}}],
])
def test_anything_but_exactly_one_store_call_is_refused(content):
    with pytest.raises(ValueError, match='expected exactly one ' + STORE_RESULT_TOOL):
        answer_from_response(_envelope(content))


@pytest.mark.parametrize('result, message', [('   ', 'empty result'), (None, 'without a string result'),
                                             (42, 'without a string result')])
def test_an_empty_or_non_string_result_is_refused(result, message):
    with pytest.raises(ValueError, match=message):
        answer_from_response(_envelope([{'type': 'tool_use', 'name': STORE_RESULT_TOOL, 'input': {'result': result}}]))


def test_the_failure_line_carries_the_wording_the_analyzers_match():
    line = api_failure_line(429, '{"type":"error","error":{"type":"rate_limit_error"}}')

    assert line.startswith('Anthropic API call failed with status 429; body=')
    assert '"type":"rate_limit_error"' in line
    assert api_failure_line(500, None).endswith('body=<no body>')
    assert api_failure_line(500, 'x' * 2500).endswith('x' * 10 + '...')


# ----------------------------------------------------------------- llm_provider

def test_llm_provider_is_cc_unless_the_meta_says_claude_api():
    assert mh_call_cc.llm_provider([]) == 'cc'
    assert mh_call_cc.llm_provider([{'llm_provider': '  '}]) == 'cc'
    assert mh_call_cc.llm_provider([{'llm_provider': 'cc'}]) == 'cc'
    assert mh_call_cc.llm_provider([{'llm_provider': ' claude_api '}]) == 'claude_api'


def test_an_unknown_llm_provider_fails_instead_of_running_cc():
    with pytest.raises(ValueError, match="'llm_provider' must be"):
        mh_call_cc.llm_provider([{'llm_provider': 'claude-api'}])


# ----------------------------------------------------------------- the secret channel

def test_read_secret_round_trip_and_zero():
    channel = ProcessorSecretChannel('check-1', 'sk-\u043a\u043b\u044e\u0447'.encode('utf-8'))
    key = read_secret(channel.port, 'check-1')

    assert key.decode('utf-8') == 'sk-\u043a\u043b\u044e\u0447'
    zero(key)
    assert all(b == 0 for b in key)


def test_a_wrong_check_code_gets_no_key():
    channel = ProcessorSecretChannel('check-1', b'sk')

    with pytest.raises(EOFError, match='wrong check code gets no key'):
        read_secret(channel.port, 'someone-else')


# ----------------------------------------------------------------- run_claude_api, end to end in a task dir

def _task(tmp_path, channel=None):
    params = {'workingPath': str(tmp_path), 'outputs': [{'id': '9', 'name': 'ccResult'}]}
    if channel is not None:
        params.update({'secretPort': channel.port, 'checkCode': channel.check_code})
    return params


def test_run_claude_api_stores_the_store_calls_result_verbatim(tmp_path):
    api = EchoMessagesApi('sk-test')
    channel = ProcessorSecretChannel('cc-1', b'sk-test')
    params = _task(tmp_path, channel)
    try:
        code = mh_call_cc.run_claude_api(params, [{'max-tokens': '200'}, {'timeout-sec': '30'}], str(tmp_path),
                                         'answer with\ntwo lines', params['outputs'][0], 'claude-haiku-5-5', None,
                                         api_url=api.url)
    finally:
        api.close()

    assert code == 0
    assert (tmp_path / 'artifacts' / '9').read_bytes() == b'answer with\ntwo lines'
    [request] = api.requests
    assert request['path'] == '/v1/messages'
    assert request['headers']['x-api-key'] == 'sk-test'
    assert request['headers']['anthropic-version'] == '2023-06-01'
    assert request['body']['model'] == 'claude-haiku-5-5'
    # plan 050 Phase 17 (rewritten 2026-10-25, section 9.3 rule 2 - was max_tokens 200 and the forced tool)
    assert request['body']['max_tokens'] == 200 + 32768
    assert request['body']['tool_choice'] == {'type': 'auto'}
    assert json.loads((tmp_path / 'cc-data' / 'api-response.json').read_text(encoding='utf-8'))['stop_reason'] == 'tool_use'
    assert 'sk-test' not in (tmp_path / 'cc-data' / 'api-response.json').read_text(encoding='utf-8')


def test_run_claude_api_with_a_rejected_key_fails_with_the_analyzer_line(tmp_path, capsys):
    api = EchoMessagesApi('sk-real')
    channel = ProcessorSecretChannel('cc-2', b'sk-revoked')
    params = _task(tmp_path, channel)
    try:
        code = mh_call_cc.run_claude_api(params, [], str(tmp_path), 'p', params['outputs'][0], 'claude-haiku-5-5', None,
                                         api_url=api.url)
    finally:
        api.close()

    assert code == 1
    console = capsys.readouterr().out
    assert 'FAILED: Anthropic API call failed with status 401; body=' in console
    assert '"authentication_error"' in console
    assert 'sk-revoked' not in console
    assert not (tmp_path / 'artifacts' / '9').exists()


def test_run_claude_api_without_a_handoff_or_a_model_fails_before_any_call(tmp_path, capsys):
    params = _task(tmp_path)

    assert mh_call_cc.run_claude_api(params, [], str(tmp_path), 'p', params['outputs'][0], 'm', None) == 1
    assert 'no API key was handed over' in capsys.readouterr().out
    assert mh_call_cc.run_claude_api(params, [], str(tmp_path), 'p', params['outputs'][0], None, None) == 1
    assert 'no model for llm_provider=claude_api' in capsys.readouterr().out


def test_run_claude_api_a_model_refusing_forced_tool_use(tmp_path, capsys):
    """Plan 050 Phase 17 (CT): a model that refuses a forced tool_choice (claude-sonnet-5-5 answered 400
    invalid_request_error) - the REPAIR step's first escalation level on the API path. Green-1 pins the behaviour."""
    api = ForcedToolRefusingApi()
    channel = ProcessorSecretChannel('cc-3', b'sk-test')
    params = _task(tmp_path, channel)
    try:
        code = mh_call_cc.run_claude_api(params, [{'timeout-sec': '30'}], str(tmp_path), 'the repair prompt',
                                         params['outputs'][0], 'claude-sonnet-5-5', None, api_url=api.url)
    finally:
        api.close()

    console = capsys.readouterr().out
    # Red (Green-1 pinned: the one forced request refused, exit 1): the refusal names tool_choice, so the same request goes
    # once more with tool_choice auto - the tool still offered, the answer still exactly one store call
    # (rewritten 2026-10-25, section 9.3 rule 2: the first and only request is tool_choice auto, so the refusal never
    # arises - the request shape every model accepts)
    assert code == 0, console
    assert (tmp_path / 'artifacts' / '9').read_bytes() == b'the repair prompt'
    assert [r['body']['tool_choice'] for r in api.requests] == [{'type': 'auto'}]
    assert api.requests[0]['body']['tools'] == [mh_api_call.store_result_tool()]
    assert 'refuses' not in console


def test_run_claude_api_with_an_effort(tmp_path, capsys):
    """Plan 050 Phase 17 (CT): the effort of a run on the API path. Every v5 - v7 analysis of r1 on the CC path (effort
    high) read "Stations act on stale prices." as a fact or a cost; four of five v8 analyses on the API path read it as an
    obligation - and declined. Green-1 pins what the API path does with an effort."""
    api = EchoMessagesApi('sk-test')
    channel = ProcessorSecretChannel('cc-4', b'sk-test')
    params = _task(tmp_path, channel)
    try:
        code = mh_call_cc.run_claude_api(params, [{'max-tokens': '200'}, {'timeout-sec': '30'}], str(tmp_path), 'p',
                                         params['outputs'][0], 'claude-opus-5-5', 'extra', api_url=api.url)
    finally:
        api.close()

    console = capsys.readouterr().out
    assert code == 0, console
    [request] = api.requests
    # Red (Green-1 pinned: the effort dropped - no thinking, the tool forced, the answer's budget only): the effort is the
    # API's extended thinking - high = 12288 thinking tokens on top of the answer's budget; thinking excludes a forced tool
    # (rewritten 2026-10-25, section 9.3 rule 2 - was haiku / high as budget_tokens 12288; its haiku case is now
    # test_run_claude_api_haiku_5_5_at_effort_high): the REPAIR ladder's level 2 - the wire code extra is the API's xhigh,
    # sent as output_config.effort, with xhigh's thinking room; no thinking field
    assert 'effort extra -> output_config.effort xhigh, adaptive thinking, max_tokens 200 + 65536' in console
    assert request['body']['output_config'] == {'effort': 'xhigh'}
    assert 'thinking' not in request['body']
    assert request['body']['tool_choice'] == {'type': 'auto'}
    assert request['body']['max_tokens'] == 200 + 65536


def test_run_claude_api_haiku_5_5_at_effort_high(tmp_path, capsys):
    """Plan 050 Phase 17 (CT): the default step's model and effort (claude-haiku-5-5 / high) on the API path, against a
    stand-in behaving as Claude Haiku 5.5 does. v8's analyses of r1 on this path (#101 - #106) all ran with 0 thinking
    tokens: the forced tool_choice starts the response with the tool call, and 1d9a018's budget_tokens thinking is a 400
    whose fallback is the forced request again. Green-1 pins what the API path sends."""
    api = Haiku55Api()
    channel = ProcessorSecretChannel('cc-5', b'sk-test')
    params = _task(tmp_path, channel)
    try:
        code = mh_call_cc.run_claude_api(params, [{'max-tokens': '200'}, {'timeout-sec': '30'}], str(tmp_path),
                                         'the analysis prompt', params['outputs'][0], 'claude-haiku-5-5', 'high',
                                         api_url=api.url)
    finally:
        api.close()

    console = capsys.readouterr().out
    assert code == 0, console
    assert (tmp_path / 'artifacts' / '9').read_bytes() == b'the analysis prompt'
    bodies = [r['body'] for r in api.requests]
    # Red (Green-1 pinned: two requests - the extended-thinking one refused, then the forced one with neither thinking nor
    # the effort): ONE request every 5.5 model accepts - no thinking field (adaptive is the default), the effort as
    # output_config.effort, the store tool under tool_choice auto (a forced tool suppresses the thinking), max_tokens the
    # answer's budget plus room for the thinking (thinking counts toward max_tokens)
    assert len(bodies) == 1, bodies
    assert 'thinking' not in bodies[0]
    assert bodies[0]['output_config'] == {'effort': 'high'}
    assert bodies[0]['tool_choice'] == {'type': 'auto'}
    assert bodies[0]['tools'] == [mh_api_call.store_result_tool()]
    assert bodies[0]['max_tokens'] == 200 + 32768
    assert 'effort high -> output_config.effort high, adaptive thinking, max_tokens 200 + 32768' in console
    assert 'refuses' not in console


def test_thinking_budget_per_effort():
    assert mh_api_call.thinking_budget(None) is None
    assert mh_api_call.thinking_budget('  ') is None
    assert mh_api_call.thinking_budget('low') == 2048
    assert mh_api_call.thinking_budget('medium') == 6144
    assert mh_api_call.thinking_budget('HIGH') == 12288
    assert mh_api_call.thinking_budget('extra') == 24576
    assert mh_api_call.thinking_budget('xhigh') == 24576
    with pytest.raises(ValueError, match='unknown effort'):
        mh_api_call.thinking_budget('maximal')


def test_request_body_with_an_effort_sends_output_config_and_adds_the_thinking_room():
    # plan 050 Phase 17 (rewritten 2026-10-25, section 9.3 rule 2 - was ..._with_thinking_...: thinking enabled with
    # budget_tokens 2048, max_tokens 2148)
    body = request_body('claude-haiku-5-5', 'p', 100, effort='low')
    assert body['output_config'] == {'effort': 'low'}
    assert 'thinking' not in body
    assert body['max_tokens'] == 100 + 8192
    assert body['tool_choice'] == {'type': 'auto'}
    assert 'output_config' not in request_body('claude-haiku-5-5', 'p', 100), 'no effort sent without one'
    assert request_body('claude-opus-5-5', 'p', 120000, effort='max')['max_tokens'] == 128000, 'capped at the ceiling'
    with pytest.raises(ValueError, match='unknown API effort'):
        request_body('claude-opus-5-5', 'p', 100, effort='extra')


def test_api_effort_per_wire_code():
    assert mh_api_call.api_effort(None) is None
    assert mh_api_call.api_effort('  ') is None
    assert [mh_api_call.api_effort(e) for e in ['low', 'medium', 'HIGH', 'extra', 'xhigh', 'max']] == \
           ['low', 'medium', 'high', 'xhigh', 'xhigh', 'max']
    with pytest.raises(ValueError, match='unknown effort'):
        mh_api_call.api_effort('maximal')


def test_thinking_room_per_api_effort():
    assert [mh_api_call.thinking_room(e) for e in [None, 'low', 'medium', 'high', 'xhigh', 'max']] == \
           [32768, 8192, 16384, 32768, 65536, 65536]


def test_refused_parameter_names_what_a_400_refuses():
    def err(message):
        return json.dumps({'type': 'error', 'error': {'type': 'invalid_request_error', 'message': message}})
    assert mh_api_call.refused_parameter(400, err(Haiku55Api.REFUSAL)) == 'thinking'
    assert mh_api_call.refused_parameter(400, err(ForcedToolRefusingApi.REFUSAL)) == 'tool_choice'
    assert mh_api_call.refused_parameter(400, err('output_config.effort: xhigh is not supported')) == 'effort'
    assert mh_api_call.refused_parameter(400, err('output_config: Extra inputs are not permitted')) == 'output_config'
    assert mh_api_call.refused_parameter(400, err('messages: at least one message is required')) is None
    assert mh_api_call.refused_parameter(500, err('thinking: overloaded')) is None


def test_thinking_refused_is_the_apis_400_naming_thinking_only():
    def err(message):
        return json.dumps({'type': 'error', 'error': {'type': 'invalid_request_error', 'message': message}})
    assert mh_api_call.thinking_refused(400, err('thinking: extended thinking is not supported for this model'))
    assert not mh_api_call.thinking_refused(400, err(ForcedToolRefusingApi.REFUSAL))
    assert not mh_api_call.thinking_refused(500, err('thinking: overloaded'))
    assert not mh_api_call.thinking_refused(400, None)


# ---------------------------------------------------------------------------------------------------
# RATE-LIMIT HEADER LINES - a contract with MH's mh-api-analyzers.yaml (rule api-request-limit): the Processor sees
# nothing of the HTTP exchange, so the Function prints, on a non-2xx response, one '<header>: <value>' line per
# rate-limit header present - name in lower case, in RATE_LIMIT_HEADERS order, nothing else.

class FixedStatusApi:
    """A local Messages API answering every POST with one fixed status, headers and JSON body."""

    def __init__(self, status, headers, payload):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                data = json.dumps(payload).encode('utf-8')
                self.send_response(status)
                for name, value in headers:
                    self.send_header(name, value)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(('127.0.0.1', 0), Handler)
        self.url = 'http://127.0.0.1:' + str(self.httpd.server_address[1]) + '/v1/messages'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


# as the API sends them: mixed case, plus headers that are not rate-limit headers
RATE_LIMIT_RESPONSE_HEADERS = [('Retry-After', '2'), ('Anthropic-RateLimit-Requests-Remaining', '0'),
                               ('anthropic-ratelimit-tokens-remaining', '380000'),
                               ('anthropic-ratelimit-input-tokens-remaining', '300000'),
                               ('anthropic-ratelimit-output-tokens-remaining', '80000'),
                               ('request-id', 'req_011'), ('anthropic-ratelimit-requests-reset', '2026-10-26T12:00:00Z')]
RATE_LIMIT_ERROR = {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': 'rate limit exceeded'}}
EXPECTED_RATE_LIMIT_LINES = ['retry-after: 2',
                             'anthropic-ratelimit-requests-remaining: 0',
                             'anthropic-ratelimit-tokens-remaining: 380000',
                             'anthropic-ratelimit-input-tokens-remaining: 300000',
                             'anthropic-ratelimit-output-tokens-remaining: 80000']


def _call_fixed_status_api(status, headers, payload):
    api = FixedStatusApi(status, headers, payload)
    try:
        return CALL(api.url)
    finally:
        api.close()


def test_a_429_prints_the_rate_limit_headers_in_contract_order(capsys):
    status, text = _call_fixed_status_api(429, RATE_LIMIT_RESPONSE_HEADERS, RATE_LIMIT_ERROR)
    assert status == 429
    assert '"rate_limit_error"' in text
    # exactly these lines: lower-case names whatever the wire case, contract order, no other header
    assert capsys.readouterr().out.splitlines() == EXPECTED_RATE_LIMIT_LINES


def test_a_spend_cap_429_has_no_retry_after_line(capsys):
    headers = [h for h in RATE_LIMIT_RESPONSE_HEADERS if h[0] != 'Retry-After']
    status, _ = _call_fixed_status_api(429, headers, {'type': 'error', 'error': {
        'type': 'rate_limit_error', 'message': 'You have reached your API usage limits',
        'details': {'error_code': 'enforced_spend_limit_reached'}}})
    assert status == 429
    assert capsys.readouterr().out.splitlines() == EXPECTED_RATE_LIMIT_LINES[1:]


def test_a_2xx_prints_no_header_lines(capsys):
    status, _ = _call_fixed_status_api(200, RATE_LIMIT_RESPONSE_HEADERS, {'ok': True})
    assert status == 200
    assert capsys.readouterr().out == ''


def test_a_non_429_failure_prints_its_headers_too(capsys):
    # every non-2xx prints them - the analyzer, not the Function, decides what a 529 with requests-remaining: 0 means
    status, _ = _call_fixed_status_api(529, [('anthropic-ratelimit-requests-remaining', '0')],
                                       {'type': 'error', 'error': {'type': 'overloaded_error', 'message': 'Overloaded'}})
    assert status == 529
    assert capsys.readouterr().out.splitlines() == ['anthropic-ratelimit-requests-remaining: 0']


def test_rate_limit_header_lines_without_headers_is_empty():
    assert MODULE.rate_limit_header_lines(None) == []
    assert MODULE.rate_limit_header_lines({}) == []

MODULE = mh_api_call


def CALL(url):
    return mh_api_call.post_messages(url, 'k', {'model': 'm'}, 5)
