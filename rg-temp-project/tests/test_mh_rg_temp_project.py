# The core of mh.asset.rg-temp-project_1.0. Every test builds the world it asserts against: values it
# writes down, an in-memory RG that keeps the one rule the create loop depends on, and a loopback HTTP
# server it starts itself. No test reaches a real RG, a dispatcher or a vault.

import base64
import http.server
import json
import secrets
import socket
import threading
import urllib.parse

import pytest

import mh_rg_temp_project as fn


# ---------------------------------------------------------------------------------------------------
# the production switch

@pytest.mark.parametrize('value, expected', [
    ('true', True), ('true\n', True), (' true ', True),
    ('True', False), ('false', False), ('mh.null-value', False), ('', False), (None, False),
])
def test_is_production_only_for_the_literal_true(value, expected):
    assert fn.is_production(value) is expected


# ---------------------------------------------------------------------------------------------------
# the draw

def test_random_code_is_the_prefix_plus_one_pick_per_position():
    assert fn.random_code(lambda alphabet: alphabet[0]) == 'TMPAAAAAAAA'


def test_random_code_from_the_real_source_fits_rg():
    code = fn.random_code(secrets.choice)

    assert len(code) == 11                     # RG refuses a code over 20
    assert code.startswith('TMP')
    assert all(c in fn.CODE_ALPHABET for c in code[3:])
    assert code == code.upper()                # RG upper-cases codes; a lower-case draw would come back changed


# ---------------------------------------------------------------------------------------------------
# the endpoint

@pytest.mark.parametrize('base, expected', [
    ('http://localhost:64967', 'http://localhost:64967/rest/v1/rg/projects/add'),
    ('http://localhost:64967/', 'http://localhost:64967/rest/v1/rg/projects/add'),
    ('  https://rg.example.com\n', 'https://rg.example.com/rest/v1/rg/projects/add'),
])
def test_create_url_appends_the_create_path(base, expected):
    assert fn.create_url(base) == expected


@pytest.mark.parametrize('base', ['localhost:64967', 'ftp://host', 'mh.null-value', '', None])
def test_create_url_refuses_what_is_not_an_absolute_http_url(base):
    with pytest.raises(ValueError, match='rg-base-url'):
        fn.create_url(base)


# ---------------------------------------------------------------------------------------------------
# the credential - plain login:password in the vault, base64 on the wire

def test_basic_authorization_base64_encodes_the_plain_login_password():
    assert fn.basic_authorization(bytearray(b'admin:secret')) == 'Basic YWRtaW46c2VjcmV0'


def test_basic_authorization_drops_a_trailing_line_break():
    assert fn.basic_authorization(bytearray(b'admin:secret\r\n')) == 'Basic YWRtaW46c2VjcmV0'


def test_basic_authorization_keeps_a_colon_inside_the_password():
    header = fn.basic_authorization(bytearray(b'admin:se:cret'))

    assert header.startswith('Basic ')
    assert base64.b64decode(header[len('Basic '):]) == b'admin:se:cret'


@pytest.mark.parametrize('value', [b'admin-secret', b':secret', b''])
def test_basic_authorization_refuses_what_is_not_login_password_without_echoing_it(value):
    with pytest.raises(ValueError, match='login:password') as e:
        fn.basic_authorization(bytearray(value))
    if value:
        assert value.decode('ascii') not in str(e.value)


# ---------------------------------------------------------------------------------------------------
# the request

def test_form_body_carries_what_rg_create_project_reads():
    assert urllib.parse.parse_qs(fn.form_body('TMPAAAAAAAA', 'ru', 42).decode('utf-8')) == {
        'name': ['Temporary project TMPAAAAAAAA'],
        'infoBank': ['TMPAAAAAAAA'],
        'locale': ['ru'],
        'description': ['Temporary project created by mh.asset.rg-temp-project_1.1 in ExecContext #42'],
    }


# ---------------------------------------------------------------------------------------------------
# RG's answer

def test_classify_created_returns_the_code_rg_answered_with():
    body = json.dumps({'errorMessages': None, 'infoMessages': None,
                       'project': {'id': 7, 'infoBank': 'TMPAAAAAAAA', 'name': 'Temporary project TMPAAAAAAAA'}})

    assert fn.classify(200, body) == (fn.CREATED, 'TMPAAAAAAAA')


@pytest.mark.parametrize('message', [
    "Info bank with code 'TMPAAAAAAAA' already exists",      # RgProjectService.createProject
    'Info bank with this code already exists',               # LegalInfoBankService.createInfoBank
])
def test_classify_a_taken_code_is_a_collision_not_a_failure(message):
    assert fn.classify(200, json.dumps({'errorMessages': [message]})) == (fn.EXISTS, None)


def test_classify_any_other_refusal_is_final_and_carries_rgs_words():
    body = json.dumps({'errorMessages': ["Locale 'xx' is not a supported language"]})

    with pytest.raises(RuntimeError, match="Locale 'xx' is not a supported language"):
        fn.classify(200, body)


@pytest.mark.parametrize('status, phrase', [(401, 'HTTP 401'), (403, 'LEGAL_ADMIN'), (500, 'HTTP 500')])
def test_classify_an_http_failure_is_final(status, phrase):
    with pytest.raises(RuntimeError, match=phrase):
        fn.classify(status, 'irrelevant')


@pytest.mark.parametrize('body', ['<html>login</html>', '[]', json.dumps({'project': {}}), json.dumps({})])
def test_classify_a_200_without_a_project_code_is_a_failure(body):
    with pytest.raises(RuntimeError):
        fn.classify(200, body)


# ---------------------------------------------------------------------------------------------------
# the mkdtemp loop

class InMemoryRg:
    """RG's create, reduced to the one rule the loop depends on: a code is created once, and creating it
    again is refused as already existing. Codes are kept the way RG keeps them, upper-cased."""

    def __init__(self):
        self.codes = set()

    def create(self, code):
        upper = code.upper()
        if upper in self.codes:
            return fn.EXISTS, None
        self.codes.add(upper)
        return fn.CREATED, upper


def draws(*codes):
    """A draw a test can predict - the same seam production feeds with random_code(secrets.choice)."""
    sequence = iter(codes)
    return lambda: next(sequence)


def test_create_takes_the_first_draw_when_it_is_free():
    rg = InMemoryRg()

    code = fn.create_temp_project(rg.create, draws('TMPAAAAAAAA', 'TMPBBBBBBBB'))

    assert code == 'TMPAAAAAAAA'
    assert rg.codes == {'TMPAAAAAAAA'}


def test_create_draws_again_when_the_code_is_taken():
    rg = InMemoryRg()
    rg.create('TMPAAAAAAAA')

    code = fn.create_temp_project(rg.create, draws('TMPAAAAAAAA', 'TMPBBBBBBBB'))

    assert code == 'TMPBBBBBBBB'
    assert rg.codes == {'TMPAAAAAAAA', 'TMPBBBBBBBB'}


def test_create_gives_up_after_max_attempts_and_creates_nothing():
    rg = InMemoryRg()
    rg.create('TMPAAAAAAAA')

    with pytest.raises(RuntimeError, match='no free project code after 3 attempts'):
        fn.create_temp_project(rg.create, lambda: 'TMPAAAAAAAA', max_attempts=3)
    assert rg.codes == {'TMPAAAAAAAA'}


def test_create_does_not_retry_a_refusal_that_is_not_a_collision():
    def refusing_rg(code):
        raise RuntimeError("RG refused to create the project: Locale 'xx' is not a supported language")

    # ONE draw only: a loop that swallowed the refusal and drew again would fail on the empty sequence
    # instead of surfacing RG's words
    with pytest.raises(RuntimeError, match="Locale 'xx'"):
        fn.create_temp_project(refusing_rg, draws('TMPAAAAAAAA'))


# ---------------------------------------------------------------------------------------------------
# the wire - post_form against a loopback server that answers every POST with what it received

class EchoHandler(http.server.BaseHTTPRequestHandler):
    """Echoes each POST as JSON. The status is 200, or <code> for a path /status/<code> - fixed
    behaviour, selected by the request rather than configured per test."""

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length') or 0)).decode('utf-8')
        status = int(self.path.rsplit('/', 1)[1]) if self.path.startswith('/status/') else 200
        answer = json.dumps({
            'method': self.command,
            'path': self.path,
            'contentType': self.headers.get('Content-Type'),
            'authorization': self.headers.get('Authorization'),
            'form': urllib.parse.parse_qs(body),
        }).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(answer)))
        self.end_headers()
        self.wfile.write(answer)

    def do_GET(self):
        status = int(self.path.rsplit('/', 1)[1]) if self.path.startswith('/status/') else 200
        answer = json.dumps({
            'method': self.command,
            'path': self.path,
            'authorization': self.headers.get('Authorization'),
        }).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(answer)))
        self.end_headers()
        self.wfile.write(answer)

    def log_message(self, fmt, *args):
        pass


@pytest.fixture
def echo_server():
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield 'http://127.0.0.1:' + str(server.server_address[1])
    server.shutdown()
    server.server_close()


def test_post_form_sends_a_form_post_with_the_authorization_header(echo_server):
    status, text = fn.post_form(echo_server + fn.CREATE_PATH, fn.form_body('TMPAAAAAAAA', 'en', 42),
                                'Basic YWRtaW46c2VjcmV0', timeout=5)
    echoed = json.loads(text)

    assert status == 200
    assert echoed['method'] == 'POST'
    assert echoed['path'] == '/rest/v1/rg/projects/add'
    assert echoed['contentType'].startswith('application/x-www-form-urlencoded')
    assert echoed['authorization'] == 'Basic YWRtaW46c2VjcmV0'
    assert echoed['form']['infoBank'] == ['TMPAAAAAAAA']
    assert echoed['form']['locale'] == ['en']


def test_post_form_returns_an_error_status_instead_of_raising(echo_server):
    status, text = fn.post_form(echo_server + '/status/401', b'x=1', 'Basic x', timeout=5)

    assert status == 401
    assert json.loads(text)['path'] == '/status/401'


def test_post_form_names_an_rg_it_cannot_reach():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    # the socket is closed: nothing listens on that port any more

    with pytest.raises(RuntimeError, match='cannot reach RG'):
        fn.post_form('http://127.0.0.1:' + str(port) + fn.CREATE_PATH, b'x=1', 'Basic x', timeout=5)


# ---------------------------------------------------------------------------------------------------
# the optional behaviour: the caller's description, maxDepth, creation in development, an RG pipeline

@pytest.mark.parametrize('production, create_in_development, expected', [
    ('true', None, True), ('false', None, False), ('false', 'true', True), ('mh.null-value', ' true ', True),
    ('false', 'false', False), ('false', 'True', False),
])
def test_should_create(production, create_in_development, expected):
    assert fn.should_create(production, create_in_development) is expected


@pytest.mark.parametrize('value, expected', [
    (None, None), ('', None), ('  ', None), ('mh.null-value', None), (' Derby \n', 'Derby'),
])
def test_optional_text(value, expected):
    assert fn.optional_text(value) == expected


@pytest.mark.parametrize('value, expected', [(None, None), ('', None), ('1', 1), (' 3 ', 3)])
def test_parse_max_depth(value, expected):
    assert fn.parse_max_depth(value) == expected


@pytest.mark.parametrize('value', ['0', '-1', 'deep'])
def test_parse_max_depth_refuses_what_is_not_a_positive_whole_number(value):
    with pytest.raises(ValueError, match='max-depth'):
        fn.parse_max_depth(value)


def test_form_body_takes_the_callers_description_and_max_depth():
    body = fn.form_body('TMPAAAAAAAA', 'en', 42, 'Requirements for java-based database Derby', 1)

    assert urllib.parse.parse_qs(body.decode('utf-8')) == {
        'name': ['Temporary project TMPAAAAAAAA'],
        'infoBank': ['TMPAAAAAAAA'],
        'locale': ['en'],
        'description': ['Requirements for java-based database Derby'],
        'maxDepth': ['1'],
    }


def test_project_id_is_the_id_rg_answered_with():
    assert fn.project_id(json.dumps({'project': {'id': 7, 'infoBank': 'TMPAAAAAAAA'}})) == 7


@pytest.mark.parametrize('body', [json.dumps({}), json.dumps({'project': {}}), '[]', 'not json'])
def test_project_id_refuses_an_answer_without_one(body):
    with pytest.raises(RuntimeError, match='no project id'):
        fn.project_id(body)


def test_rg_json_returns_the_answer_when_rg_reports_no_error():
    assert fn.rg_json(200, json.dumps({'errorMessages': None, 'sourceCodes': []}), 'x') == \
        {'errorMessages': None, 'sourceCodes': []}


@pytest.mark.parametrize('status, body, phrase', [
    (200, json.dumps({'errorMessages': ['04.812.200 frozen']}), '04.812.200 frozen'),
    (401, '', 'HTTP 401'),
    (403, '', 'LEGAL_ADMIN'),
    (500, 'boom', 'HTTP 500'),
    (200, '<html/>', 'not JSON'),
])
def test_rg_json_raises_naming_the_call_and_what_rg_said(status, body, phrase):
    with pytest.raises(RuntimeError, match=phrase) as e:
        fn.rg_json(status, body, 'assign SourceCode to TMPAAAAAAAA')
    assert 'assign SourceCode to TMPAAAAAAAA' in str(e.value)


def test_source_code_id_for_picks_the_uid():
    answer = {'sourceCodes': [{'sourceCodeId': 8, 'uid': 'mhdg-rg-cc-1.0.76'},
                              {'sourceCodeId': 17, 'uid': 'mhdg-rg-synthetic-1.0.76'}]}

    assert fn.source_code_id_for('mhdg-rg-synthetic-1.0.76', answer) == 17


def test_source_code_id_for_names_what_rg_offers_when_the_uid_is_not_there():
    with pytest.raises(RuntimeError, match='mhdg-rg-cc-1.0.76') as e:
        fn.source_code_id_for('mhdg-rg-cc-9.9', {'sourceCodes': [{'sourceCodeId': 8, 'uid': 'mhdg-rg-cc-1.0.76'}]})
    assert 'mhdg-rg-cc-9.9' in str(e.value)


def test_the_pipeline_calls():
    assert fn.rg_base(' http://localhost:64967/ ') == 'http://localhost:64967'
    assert fn.source_codes_url('http://localhost:64967', 'TMPAAAAAAAA') == \
        'http://localhost:64967/rest/v1/rg/projects/TMPAAAAAAAA/source-codes'
    assert fn.task_url('http://localhost:64967', 7) == 'http://localhost:64967/rest/v1/rg/projects/7/task'
    assert urllib.parse.parse_qs(fn.task_body(8, 'Requirements for java-based database Derby').decode('utf-8')) == {
        'task': ['Requirements for java-based database Derby'], 'sourceCodeId': ['8'], 'isReady': ['true']}


@pytest.mark.parametrize('task', [None, '', '   '])
def test_task_body_refuses_an_empty_task_because_rg_would_silently_leave_the_project_not_ready(task):
    with pytest.raises(ValueError, match='task text'):
        fn.task_body(8, task)


def test_http_get_sends_the_authorization_header(echo_server):
    status, text = fn.http_get(echo_server + '/rest/v1/rg/projects/TMPAAAAAAAA/source-codes',
                               'Basic YWRtaW46c2VjcmV0', timeout=5)
    echoed = json.loads(text)

    assert status == 200
    assert echoed['method'] == 'GET'
    assert echoed['authorization'] == 'Basic YWRtaW46c2VjcmV0'


def test_http_get_returns_an_error_status_instead_of_raising(echo_server):
    status, _ = fn.http_get(echo_server + '/status/404', 'Basic x', timeout=5)

    assert status == 404
