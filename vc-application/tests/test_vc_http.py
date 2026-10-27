# Unit tests of vc_http.py against a loopback HTTP server each test starts itself - a real server and a real
# socket, nothing patched. The guard (may_send) is the session's caller's; here it is a plain function.

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import vc_http


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _record(self, body=None):
        # header names are case-insensitive (urllib sends X-Csrf-Token for X-CSRF-Token): stored lower-cased
        self.server.seen.append((self.command, self.path, {k.lower(): v for k, v in self.headers.items()}, body))

    def do_GET(self):
        self._record()
        path = self.path.split('?')[0]
        if path == '/set-cookie':
            self.send_response(200)
            self.send_header('Set-Cookie', 'session=abc123; Path=/')
            self.end_headers()
            self.wfile.write(b'ok')
        elif path == '/redirect-to-refused':
            self.send_response(302)
            self.send_header('Location', '/refused/target')
            self.end_headers()
        elif path == '/redirect-to-allowed':
            self.send_response(302)
            self.send_header('Location', '/allowed/target')
            self.end_headers()
        elif path == '/missing':
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'not here')
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(('cookie=' + str(self.headers.get('Cookie'))).encode('utf-8'))

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length') or 0)).decode('utf-8')
        self._record(body)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'echo': json.loads(body)}).encode('utf-8'))


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    httpd.seen = []
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def base(server):
    return 'http://127.0.0.1:' + str(server.server_address[1])


def allow_all(method, url):
    return True


def test_describe_drops_the_query():
    assert vc_http.describe('GET', 'https://account.example/?continue=https%3A%2F%2Fx') == 'GET account.example/'
    assert vc_http.describe('POST', 'https://account.example/sign_in?a=1') == 'POST account.example/sign_in'


def test_cookie_set_by_one_response_is_sent_with_the_next(server):
    session = vc_http.open_session(allow_all, lambda line: None)
    session.get(base(server) + '/set-cookie')
    second = session.get(base(server) + '/echo')
    assert session.cookie('session') == 'abc123'
    assert second.text == 'cookie=session=abc123'


def test_post_json_sends_a_json_body_with_the_callers_headers(server):
    session = vc_http.open_session(allow_all, lambda line: None)
    answer = session.post_json(base(server) + '/start', {'ycid': 'founder'}, {'X-CSRF-Token': 't1'})
    method, path, headers, body = server.seen[-1]
    assert (method, path) == ('POST', '/start')
    assert json.loads(body) == {'ycid': 'founder'}
    assert headers['content-type'] == 'application/json'
    assert headers['x-csrf-token'] == 't1'
    assert json.loads(answer.text) == {'echo': {'ycid': 'founder'}}


def test_http_error_status_is_returned_not_raised(server):
    session = vc_http.open_session(allow_all, lambda line: None)
    answer = session.get(base(server) + '/missing')
    assert answer.status == 404
    assert answer.text == 'not here'


def test_refused_request_never_reaches_the_server(server):
    session = vc_http.open_session(lambda method, url: method == 'GET', lambda line: None)
    with pytest.raises(vc_http.RequestRefused) as e:
        session.post_json(base(server) + '/apps/x', {'answer': 'x'})
    assert 'POST 127.0.0.1' in str(e.value)
    assert server.seen == []


def test_refused_redirect_is_not_followed(server):
    session = vc_http.open_session(lambda method, url: '/refused/' not in url, lambda line: None)
    with pytest.raises(vc_http.RequestRefused) as e:
        session.get(base(server) + '/redirect-to-refused')
    assert '/refused/target' in str(e.value)
    assert [p for _, p, _, _ in server.seen] == ['/redirect-to-refused']


def test_allowed_redirect_is_followed_and_logged(server):
    lines = []
    session = vc_http.open_session(allow_all, lines.append)
    answer = session.get(base(server) + '/redirect-to-allowed?token=secret')
    assert answer.status == 200
    assert answer.url.endswith('/allowed/target')
    assert [p for _, p, _, _ in server.seen] == ['/redirect-to-allowed?token=secret', '/allowed/target']
    assert lines[0] == 'GET 127.0.0.1:' + str(server.server_address[1]) + '/redirect-to-allowed'
    assert lines[1].startswith('  redirect 302 -> GET ')
    assert all('secret' not in line for line in lines)
