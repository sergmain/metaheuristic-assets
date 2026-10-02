# Synthetic unit tests of mh.asset.mh-api-probe_1.0. Every fixture is built here; nothing reads real data, and
# the only HTTP server is a loopback one these tests start themselves.

import base64
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import mh_api_probe as p

CREDENTIAL = b'synthetic-admin:pass:with:colons'
PATH = '/rest/v1/dispatcher/meta-storage/meta-tables'
BODY = json.dumps({'production': False, 'acrossCompanies': True, 'tables': [{'type': 'a'}, {'type': 'b'}]})


# ---------------------------------------------------------------- a loopback MH that checks HTTP Basic

class _Handler(BaseHTTPRequestHandler):
    expected = 'Basic ' + base64.b64encode(CREDENTIAL).decode('ascii')
    seen = []

    def do_GET(self):
        _Handler.seen.append(self.path)
        ok = self.headers.get('Authorization') == _Handler.expected
        payload = (BODY if ok else '{"error":"unauthorized"}').encode('utf-8')
        self.send_response(200 if ok else 401)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def mh():
    server = HTTPServer(('127.0.0.1', 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _Handler.seen = []
    yield 'http://127.0.0.1:' + str(server.server_address[1])
    server.shutdown()
    server.server_close()


# ---------------------------------------------------------------- pure core

def test_is_production_only_for_exact_true():
    assert p.is_production('true')
    assert p.is_production(' true\n')
    for value in (None, '', 'false', 'TRUE', 'True', 'yes', 'mh.null-value'):
        assert not p.is_production(value), value


def test_probe_url_development_and_production():
    assert p.probe_url('http://localhost:64967/', PATH, False) == 'http://localhost:64967' + PATH + '?production=false'
    assert p.probe_url(' https://mh.example ', PATH, True) == 'https://mh.example' + PATH + '?production=true'


def test_probe_url_refuses_a_non_http_base_and_a_relative_path():
    with pytest.raises(ValueError, match='mh-base-url'):
        p.probe_url('localhost:64967', PATH, False)
    with pytest.raises(ValueError, match='mh-base-url'):
        p.probe_url(None, PATH, False)
    with pytest.raises(ValueError, match='api-path'):
        p.probe_url('http://localhost:64967', 'rest/v1/x', False)


def test_basic_authorization_encodes_the_plain_pair_and_keeps_colons_in_the_password():
    assert p.basic_authorization(bytearray(CREDENTIAL)) == 'Basic ' + base64.b64encode(CREDENTIAL).decode('ascii')


def test_basic_authorization_drops_a_pasted_line_break():
    assert p.basic_authorization(bytearray(CREDENTIAL + b'\r\n')) == p.basic_authorization(bytearray(CREDENTIAL))


def test_basic_authorization_refusal_never_contains_the_value():
    for bad in (b'no-colon-secret-value', b':secret-value'):
        with pytest.raises(ValueError) as e:
            p.basic_authorization(bytearray(bad))
        assert 'secret-value' not in str(e.value)


def test_check_answer_accepts_200_json_only():
    assert p.check_answer(200, BODY, 'u')['tables'][1] == {'type': 'b'}
    with pytest.raises(RuntimeError, match='HTTP 401'):
        p.check_answer(401, '{"error":"unauthorized"}', 'u')
    with pytest.raises(RuntimeError, match='not JSON'):
        p.check_answer(200, '<html>login</html>', 'u')


def test_summary_reports_shape_not_values():
    s = p.summary(json.loads(BODY))
    assert s == "keys ['acrossCompanies', 'production', 'tables'], list sizes {'tables': 2}"


# ---------------------------------------------------------------- http_get against the loopback MH

def test_http_get_returns_200_with_the_right_credential(mh):
    status, text = p.http_get(mh + PATH + '?production=false', p.basic_authorization(bytearray(CREDENTIAL)))
    assert status == 200
    assert json.loads(text)['acrossCompanies'] is True


def test_http_get_returns_401_rather_than_raising(mh):
    status, _ = p.http_get(mh + PATH, p.basic_authorization(bytearray(b'other:password')))
    assert status == 401


def test_http_get_unreachable_is_a_runtime_error():
    with pytest.raises(RuntimeError, match='cannot reach MH'):
        p.http_get('http://127.0.0.1:1' + PATH, 'Basic eDp5', timeout=2)


# ---------------------------------------------------------------- run: the task-params layout, end to end

def _task(work_dir, base_url, production_empty):
    variable_dir = os.path.join(work_dir, 'variable')
    os.makedirs(variable_dir, exist_ok=True)
    with open(os.path.join(variable_dir, '11'), 'w', encoding='utf-8') as f:
        f.write(base_url)
    return {
        'workingPath': work_dir,
        'metas': [{'api-path': PATH}, {'variable-for-mh-base-url': 'mhBaseUrl'},
                  {'variable-for-production': 'production'}, {'variable-for-result': 'metaTables'}],
        'inputs': [{'id': 11, 'name': 'mhBaseUrl', 'dataType': 'variable'},
                   {'id': 12, 'name': 'production', 'dataType': 'variable', 'empty': production_empty}],
        'outputs': [{'id': 21, 'name': 'metaTables', 'dataType': 'variable'}],
    }


def test_run_writes_the_answer_and_asks_for_the_synthetic_view_when_production_is_null(mh, tmp_path):
    work_dir = str(tmp_path)
    assert p.run(_task(work_dir, mh, production_empty=True), bytearray(CREDENTIAL)) == 0
    assert _Handler.seen == [PATH + '?production=false']
    with open(os.path.join(work_dir, 'artifacts', '21'), 'r', encoding='utf-8') as f:
        assert f.read() == BODY


def test_run_fails_on_a_refused_credential_and_writes_nothing(mh, tmp_path):
    work_dir = str(tmp_path)
    with pytest.raises(RuntimeError, match='HTTP 401'):
        p.run(_task(work_dir, mh, production_empty=True), bytearray(b'other:password'))
    assert not os.path.exists(os.path.join(work_dir, 'artifacts', '21'))


def test_run_without_a_credential_names_the_key_code(mh, tmp_path):
    with pytest.raises(ValueError, match='MH_API_AUTH'):
        p.run(_task(str(tmp_path), mh, production_empty=True), None)


def test_run_reports_a_missing_meta_by_listing_what_was_declared(mh, tmp_path):
    task = _task(str(tmp_path), mh, production_empty=True)
    task['metas'] = [m for m in task['metas'] if 'api-path' not in m]
    with pytest.raises(ValueError, match="meta 'api-path' is required"):
        p.run(task, bytearray(CREDENTIAL))
