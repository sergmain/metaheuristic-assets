# The MCP client: the pure parsing of what a Streamable HTTP server answers, and the protocol itself against a
# loopback server that follows the rules RG's endpoint follows - the same for every test, never programmed per test.

import http.server
import json
import threading
import time

import pytest

import mh_rg_mcp_client as fn

AUTH = 'Basic dGVzdDp0ZXN0'


# ---------------------------------------------------------------------------------------------------
# Server-Sent Events

def test_sse_events_are_the_data_of_each_event_in_order():
    stream = 'event: message\ndata: {"a":1}\n\nevent: message\ndata: {"b":2}\n\n'

    assert fn.sse_events(stream) == ['{"a":1}', '{"b":2}']


def test_sse_events_join_multi_line_data_and_ignore_other_fields():
    stream = ': a comment\r\nid: 7\r\ndata: {"a":\r\ndata:  1}\r\n\r\n'

    assert fn.sse_events(stream) == ['{"a":\n 1}']


def test_sse_events_keep_a_last_event_without_its_empty_line():
    assert fn.sse_events('data: {"a":1}') == ['{"a":1}']


def test_sse_events_keep_u2028_inside_the_data():
    # splitlines would break the JSON at U+2028; the SSE framing is newline only
    payload = json.dumps({'text': 'a\u2028b'}, ensure_ascii=False)

    assert fn.sse_events('data: ' + payload + '\n\n') == [payload]


# ---------------------------------------------------------------------------------------------------
# JSON-RPC messages, answers, tool results

def test_jsonrpc_messages_of_a_json_body_a_batch_an_sse_stream_and_nothing():
    assert fn.jsonrpc_messages('application/json', '{"id":1}') == [{'id': 1}]
    assert fn.jsonrpc_messages('application/json', '[{"id":1},{"id":2}]') == [{'id': 1}, {'id': 2}]
    assert fn.jsonrpc_messages('text/event-stream;charset=UTF-8', 'data: {"id":3}\n\n') == [{'id': 3}]
    assert fn.jsonrpc_messages('application/json', '  ') == []


def test_answer_to_skips_notifications_and_other_answers():
    messages = [{'method': 'notifications/progress'}, {'id': 2, 'result': {}}, {'id': 1, 'result': {'x': 1}}]

    assert fn.answer_to(messages, 1) == {'id': 1, 'result': {'x': 1}}


def test_answer_to_refuses_a_stream_without_the_answer():
    with pytest.raises(RuntimeError, match='no answer to request 5'):
        fn.answer_to([{'id': 1, 'result': {}}], 5)


def text_result(text, is_error=False):
    return {'id': 1, 'result': {'content': [{'type': 'text', 'text': text}], 'isError': is_error}}


def test_tool_result_is_the_json_object_in_the_text_content():
    # RG's toCallToolResult: the result object, pretty-printed, as the one text content
    answer = text_result(json.dumps({'stageSnapshotId': 12, 'parentSnapshotId': 11}, indent=2))

    assert fn.tool_result(answer, 'mhdg_rg_open_stage') == {'stageSnapshotId': 12, 'parentSnapshotId': 11}


def test_tool_result_prefers_structured_content():
    answer = {'id': 1, 'result': {'structuredContent': {'a': 1}, 'content': [{'type': 'text', 'text': '{"b":2}'}]}}

    assert fn.tool_result(answer, 't') == {'a': 1}


def test_tool_result_refuses_a_result_flagged_as_error_with_the_servers_words():
    # RG's authoringGuarded: the exception's message as text, isError true
    with pytest.raises(RuntimeError, match='mhdg_rg_seal_snapshot failed: 689.030 productArtifact'):
        fn.tool_result(text_result('689.030 productArtifact is sealed only by produce', True), 'mhdg_rg_seal_snapshot')


def test_tool_result_refuses_a_jsonrpc_error():
    with pytest.raises(RuntimeError, match=r't: MCP error -32602 Invalid params'):
        fn.tool_result({'id': 1, 'error': {'code': -32602, 'message': 'Invalid params'}}, 't')


def test_tool_result_refuses_a_result_with_no_json_object():
    with pytest.raises(RuntimeError, match='answered no JSON object: done'):
        fn.tool_result(text_result('done'), 't')


# ---------------------------------------------------------------------------------------------------
# the protocol, against a loopback server that keeps RG's rules

class McpLikeHandler(http.server.BaseHTTPRequestHandler):
    """initialize answers JSON and sets Mcp-Session-Id; a notification gets 202; tools/call needs that session and
    the credential and answers as Server-Sent Events. Tool 'echo' returns its arguments, 'broken' fails, 'lingering'
    keeps the stream open after answering. Every request is recorded as (method, session header)."""

    SESSION = 'session-1'

    def log_message(self, *args):
        pass

    def do_POST(self):
        message = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        method = message.get('method')
        session = self.headers.get('Mcp-Session-Id')
        self.server.seen.append((method, session))
        if self.headers.get('Authorization') != AUTH:
            return self._send(401, 'application/json', b'{}')
        if method == 'initialize':
            body = {'jsonrpc': '2.0', 'id': message['id'],
                    'result': {'protocolVersion': fn.PROTOCOL_VERSION, 'capabilities': {'tools': {}},
                               'serverInfo': {'name': 'loopback', 'version': '1'}}}
            return self._send(200, 'application/json', json.dumps(body).encode('utf-8'), {'Mcp-Session-Id': self.SESSION})
        if session != self.SESSION:
            return self._send(404, 'application/json', b'{"error":"unknown session"}')
        if 'id' not in message:
            return self._send(202, None, b'')
        name = message['params']['name']
        arguments = message['params']['arguments']
        if name == 'broken':
            result = {'content': [{'type': 'text', 'text': 'something failed'}], 'isError': True}
        else:
            result = {'content': [{'type': 'text', 'text': json.dumps({'got': arguments})}], 'isError': False}
        event = 'event: message\ndata: ' + json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result}) + '\n\n'
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        self.wfile.write(event.encode('utf-8'))
        self.wfile.flush()
        if name == 'lingering':
            time.sleep(3)

    def _send(self, status, content_type, body, headers=None):
        self.send_response(status)
        if content_type:
            self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), McpLikeHandler)
    httpd.daemon_threads = True
    httpd.seen = []
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()


def url_of(httpd):
    return 'http://127.0.0.1:' + str(httpd.server_address[1]) + '/rest/v1/legal/mcp'


def test_call_tool_initializes_then_calls_in_that_session(server):
    result = fn.call_tool(url_of(server), AUTH, 'echo', {'infoBank': 'TMP1', 'parentSnapshotId': 11}, 10)

    assert result == {'got': {'infoBank': 'TMP1', 'parentSnapshotId': 11}}
    assert server.seen == [('initialize', None), ('notifications/initialized', 'session-1'), ('tools/call', 'session-1')]


def test_call_tool_carries_the_servers_words_when_the_tool_fails(server):
    with pytest.raises(RuntimeError, match='broken failed: something failed'):
        fn.call_tool(url_of(server), AUTH, 'broken', {}, 10)


def test_call_tool_returns_at_the_answer_even_if_the_stream_stays_open(server):
    started = time.time()

    result = fn.call_tool(url_of(server), AUTH, 'lingering', {'x': 1}, 10)

    assert result == {'got': {'x': 1}}
    assert time.time() - started < 2, 'the client waited for the stream to close instead of stopping at its answer'


def test_call_tool_names_a_rejected_credential(server):
    with pytest.raises(RuntimeError, match='rejected the credential'):
        fn.call_tool(url_of(server), 'Basic d3Jvbmc6d3Jvbmc=', 'echo', {}, 10)
