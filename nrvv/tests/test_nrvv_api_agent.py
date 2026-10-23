# plan 052 Phase 3 - the claude_api path of mh.asset.nrvv-implement: nrvv_api_agent's tools, confinement and loop, and
# nrvv_implement.run_api end to end against a local Messages API and the Processor's secret protocol.
#
# The one stand-in model, AdderAgent, behaves the same in every test: write app.py with `add`, run the tests, end the
# turn quoting the first line of the test result. What differs is the world each test builds (its synthetic suite),
# so every summary below reports what REAL pytest said about what was REALLY written into the target dir.

import json
import os
import socket
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import nrvv_api_agent as api
import nrvv_implement as im
from conftest import write

ADDER = 'def add(a, b):\n    return a + b\n'
SUITE_ADD = {'tests/test_add.py': 'from app import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n'}
SUITE_ADD_AND_MUL = dict(SUITE_ADD, **{'tests/test_mul.py': 'import app\n\n\ndef test_mul():\n'
                                                            '    assert app.mul(2, 3) == 6\n'})


class AdderAgent:
    """turn 1: write_file app.py; turn 2: run_tests; turn 3: end the turn, quoting the test result's first line."""

    @staticmethod
    def respond(body):
        messages = body['messages']
        turn = sum(1 for m in messages if m['role'] == 'assistant') + 1
        if turn == 1:
            return 200, _envelope([{'type': 'tool_use', 'id': 'w', 'name': 'write_file',
                                    'input': {'path': 'app.py', 'content': ADDER}}], 'tool_use')
        if turn == 2:
            return 200, _envelope([{'type': 'tool_use', 'id': 'r', 'name': 'run_tests', 'input': {}}], 'tool_use')
        result = messages[-1]['content'][0]['content']
        return 200, _envelope([{'type': 'text', 'text': 'wrote app.py; ' + result.splitlines()[0]}], 'end_turn')


def _envelope(content, stop_reason):
    return json.dumps({'content': content, 'stop_reason': stop_reason, 'usage': {'output_tokens': 1}})


def world(tmp_path, suite):
    test_suite_dir, target_dir = str(tmp_path / 'test-suite'), str(tmp_path / 'target')
    write(test_suite_dir, suite)
    os.makedirs(target_dir)
    env = im.session_env(os.environ, target_dir, sys.executable)
    return test_suite_dir, target_dir, api.pytest_runner(sys.executable, test_suite_dir, target_dir, env, 120)


def loop(target_dir, run_tests, post=None, max_turns=10):
    body = api.first_request('claude-haiku-5-5', 'the prompt', 1000)
    return api.run_loop(post or (lambda b, s: AdderAgent.respond(b)), body, target_dir, run_tests, max_turns,
                        time.monotonic() + 120, log=lambda line: None)


# ----------------------------------------------------------------- provider, request, turns

def test_llm_provider_is_cc_unless_the_meta_says_claude_api():
    assert api.llm_provider(None) == 'cc' and api.llm_provider('  ') == 'cc' and api.llm_provider('cc') == 'cc'
    assert api.llm_provider(' claude_api ') == 'claude_api'
    with pytest.raises(ValueError, match="'llm_provider' must be"):
        api.llm_provider('claude-api')


def test_the_first_request_caches_the_prompt_and_offers_the_five_tools():
    body = api.first_request(' claude-haiku-5-5 ', 'p \u2014 \u00fc', 100)

    assert (body['model'], body['max_tokens']) == ('claude-haiku-5-5', 100)
    assert body['messages'] == [{'role': 'user', 'content': [{'type': 'text', 'text': 'p \u2014 \u00fc',
                                                              'cache_control': {'type': 'ephemeral'}}]}]
    assert [t['name'] for t in body['tools']] == ['list_files', 'read_file', 'write_file', 'edit_file', 'run_tests']
    with pytest.raises(ValueError, match='a model is required'):
        api.first_request(' ', 'p', 100)


def test_next_messages_answers_every_tool_call_in_order():
    envelope = {'content': [{'type': 'text', 'text': 'x'}, {'type': 'tool_use', 'id': 'a'}, {'type': 'tool_use', 'id': 'b'}]}

    messages = api.next_messages([{'role': 'user', 'content': 'p'}], envelope, [('a', 'one', False), ('b', 'two', True)])

    assert messages[1] == {'role': 'assistant', 'content': envelope['content']}
    assert messages[2] == {'role': 'user', 'content': [
        {'type': 'tool_result', 'tool_use_id': 'a', 'content': 'one', 'is_error': False},
        {'type': 'tool_result', 'tool_use_id': 'b', 'content': 'two', 'is_error': True}]}


# ----------------------------------------------------------------- confinement and tools

@pytest.mark.parametrize('rel', ['', '  ', 'C:/x.py', '/etc/passwd', '\\x.py', '../outside.py', 'sub/../../outside.py'])
def test_confined_refuses_every_path_out_of_the_target_dir(tmp_path, rel):
    with pytest.raises(api.ToolError):
        api.confined(str(tmp_path), rel)


def test_confined_resolves_a_relative_path_inside(tmp_path):
    assert api.confined(str(tmp_path), 'pkg/../app.py') == os.path.realpath(str(tmp_path / 'app.py'))


def test_write_read_edit_and_list_work_inside_the_target_dir(tmp_path):
    target = str(tmp_path)

    assert api.run_tool('write_file', {'path': 'pkg/app.py', 'content': 'a = 1\nb = 2\n'}, target, None) == \
        ('wrote 12 bytes to pkg/app.py', False)
    assert api.run_tool('edit_file', {'path': 'pkg/app.py', 'old': 'b = 2', 'new': 'b = 3'}, target, None)[1] is False
    assert api.run_tool('read_file', {'path': 'pkg/app.py'}, target, None) == ('a = 1\nb = 3\n', False)
    (tmp_path / '__pycache__').mkdir()
    (tmp_path / '__pycache__' / 'x.pyc').write_bytes(b'\0')
    assert api.run_tool('list_files', {}, target, None) == ('pkg/app.py', False)


def test_a_failing_tool_call_is_an_error_result_not_an_exception(tmp_path):
    target = str(tmp_path)
    api.run_tool('write_file', {'path': 'app.py', 'content': 'x = 1\nx = 1\n'}, target, None)

    assert api.run_tool('edit_file', {'path': 'app.py', 'old': 'x = 1', 'new': 'y'}, target, None) == \
        ('error: old occurs 2 times, it must occur exactly once', True)
    assert api.run_tool('write_file', {'path': '../out.py', 'content': 'x'}, target, None)[1] is True
    assert api.run_tool('read_file', {'path': 'absent.py'}, target, None) == ('error: no such file: absent.py', True)
    assert api.run_tool('bash', {'command': 'rm -rf /'}, target, None) == ('error: no such tool: bash', True)
    assert not (tmp_path.parent / 'out.py').exists()


def test_run_tests_runs_the_suite_against_the_target_dir(tmp_path):
    _, target_dir, run_tests = world(tmp_path, SUITE_ADD)
    api.run_tool('write_file', {'path': 'app.py', 'content': ADDER}, target_dir, None)

    result, is_error = api.run_tool('run_tests', {}, target_dir, run_tests)

    assert is_error is False and result.startswith('exit code 0\n') and '1 passed' in result
    assert api.run_tool('run_tests', {'file': 'tests/test_add.py'}, target_dir, run_tests)[0].startswith('exit code 0')
    assert api.run_tool('run_tests', {'file': 'tests/absent.py'}, target_dir, run_tests)[1] is True


# ----------------------------------------------------------------- the loop

def test_the_loop_writes_runs_and_ends_with_the_models_summary(tmp_path):
    _, target_dir, run_tests = world(tmp_path, SUITE_ADD)

    summary = loop(target_dir, run_tests)

    assert summary == 'wrote app.py; exit code 0'
    assert (tmp_path / 'target' / 'app.py').read_text(encoding='utf-8') == ADDER


def test_the_summary_reports_what_the_suite_really_said(tmp_path):
    _, target_dir, run_tests = world(tmp_path, SUITE_ADD_AND_MUL)

    assert loop(target_dir, run_tests) == 'wrote app.py; exit code 1'


def test_the_loop_stops_on_a_rejected_call_a_cut_answer_and_spent_turns(tmp_path):
    _, target_dir, run_tests = world(tmp_path, SUITE_ADD)

    with pytest.raises(api.AgentError, match='^Anthropic API call failed with status 401; body=denied$'):
        loop(target_dir, run_tests, post=lambda b, s: (401, 'denied'))
    with pytest.raises(api.AgentError, match='hit max_tokens'):
        loop(target_dir, run_tests, post=lambda b, s: (200, _envelope([{'type': 'tool_use', 'id': 'w',
             'name': 'write_file', 'input': {'path': 'app.py'}}], 'max_tokens')))
    with pytest.raises(api.AgentError, match='all 2 turns'):
        loop(target_dir, run_tests, max_turns=2)


# ----------------------------------------------------------------- run_api end to end: secret channel + HTTP + loop

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
            (n,) = struct.unpack('>i', conn.recv(4))
            if conn.recv(n).decode('utf-8') == self.check_code:
                conn.sendall(struct.pack('>i', len(self.key)) + self.key)
        self.server.close()


class AdderApi:
    """AdderAgent behind HTTP; a request without the key it was built with gets 401 authentication_error."""

    def __init__(self, valid_key):
        self.keys = []
        api_ = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])).decode('utf-8'))
                api_.keys.append(self.headers.get('x-api-key'))
                status, text = (AdderAgent.respond(body) if self.headers.get('x-api-key') == valid_key else
                                (401, '{"type":"error","error":{"type":"authentication_error"}}'))
                data = text.encode('utf-8')
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


def run_api(tmp_path, key, valid_key='sk-test', model='claude-haiku-5-5', handoff=True):
    test_suite_dir, target_dir, _ = world(tmp_path, SUITE_ADD)
    server, channel = AdderApi(valid_key), ProcessorSecretChannel('cc-1', key)
    task = {'metas': [{'llm_provider': 'claude_api'}, {'timeout-sec': '120'}]}
    if handoff:
        task.update({'secretPort': channel.port, 'checkCode': 'cc-1'})
    summary = tmp_path / 'summary.txt'
    try:
        code = im.run_api(task, 'the prompt', target_dir, test_suite_dir, model, None, str(summary), api_url=server.url)
    finally:
        server.close()
    return code, summary, server.keys


def test_run_api_drives_the_loop_with_the_handed_off_key_and_stores_the_summary(tmp_path):
    code, summary, keys = run_api(tmp_path, b'sk-test')

    assert code == 0
    assert summary.read_text(encoding='utf-8') == 'wrote app.py; exit code 0'
    assert keys == ['sk-test'] * 3


def test_run_api_with_a_rejected_key_fails_with_the_analyzer_line(tmp_path, capsys):
    code, summary, _ = run_api(tmp_path, b'sk-revoked')

    assert code == 1 and not summary.exists()
    console = capsys.readouterr().out
    assert 'FAILED: Anthropic API call failed with status 401; body=' in console and 'sk-revoked' not in console


def test_run_api_without_a_model_or_a_handoff_fails_before_any_call(tmp_path, capsys):
    assert run_api(tmp_path / 'a', b'sk-test', model=None)[0] == 1
    assert 'no model for llm_provider=claude_api' in capsys.readouterr().out
    assert run_api(tmp_path / 'b', b'sk-test', handoff=False)[0] == 1
    assert 'no API key was handed over' in capsys.readouterr().out
