# The store Function's core. The chain is exercised against an in-memory RG that keeps the two rules it depends
# on; the wire against a loopback HTTP server the tests start themselves. No test reaches a real RG or vault.

import http.server
import json
import threading

import pytest

import mh_rg_req_store as fn

REQ = {'name': 'Build with Ant', 'content': 'Derby shall build with Apache Ant.', 'rationale': 'BUILDING.html says so.'}


def answer(*reqs):
    return json.dumps(list(reqs))


# ---------------------------------------------------------------------------------------------------
# CC's answer

def test_parse_requirements_takes_a_json_array():
    assert fn.parse_requirements(answer(REQ)) == [
        {'name': 'Build with Ant', 'content': 'Derby shall build with Apache Ant.', 'rationale': 'BUILDING.html says so.'}]


def test_parse_requirements_unwraps_a_markdown_fence():
    assert fn.parse_requirements('```json\n' + answer(REQ) + '\n```') == fn.parse_requirements(answer(REQ))


def test_parse_requirements_keeps_a_missing_name_as_none():
    unnamed = {'content': REQ['content'], 'rationale': REQ['rationale']}

    assert fn.parse_requirements(answer(unnamed))[0]['name'] is None


@pytest.mark.parametrize('text, phrase', [
    ('not json', 'not JSON'),
    ('[]', 'no requirements'),
    ('{"content": "a b c"}', 'no requirements'),
    (answer('text'), '#1 is not an object'),
    (answer(dict(REQ, content='too short')), '#1 content must be text of at least 3 words'),
    (answer(dict(REQ, rationale='  ')), '#1 has no rationale'),
    (answer(REQ, dict(REQ, content=None)), '#2 content'),
])
def test_parse_requirements_refuses_before_anything_is_stored(text, phrase):
    with pytest.raises(ValueError, match=phrase):
        fn.parse_requirements(text)


# ---------------------------------------------------------------------------------------------------
# the calls

def test_the_two_bodies():
    req = fn.parse_requirements(answer(REQ))[0]

    assert fn.first_body(req) == {'content': REQ['content'], 'name': REQ['name'], 'rationale': REQ['rationale']}
    assert fn.next_body(req, 11) == {'content': REQ['content'], 'name': REQ['name'], 'parentReqId': '',
                                     'parentKind': 'SECTION', 'rationale': REQ['rationale'], 'snapshotId': 11}


def test_the_two_urls():
    assert fn.first_url('http://localhost:64967', 'TMPAAAAAAAA') == \
        'http://localhost:64967/rest/v1/rg/TMPAAAAAAAA/requirements/manual/first'
    assert fn.next_url('http://localhost:64967', 'TMPAAAAAAAA') == \
        'http://localhost:64967/rest/v1/rg/TMPAAAAAAAA/requirements/manual'


def test_created_is_the_requirement_id_and_the_committed_snapshot():
    body = json.dumps({'errorMessages': None, 'reqId': 'TMPAAAAAAAA-1', 'message': 'Created', 'documentId': 3,
                       'snapshotId': 10})

    assert fn.created(200, body) == ('TMPAAAAAAAA-1', 10)


@pytest.mark.parametrize('status, body, phrase', [
    (200, json.dumps({'errorMessages': ['04.876.035 ERROR: no SourceCode']}), '04.876.035'),
    (200, json.dumps({'reqId': '', 'snapshotId': 10}), 'no requirement id'),
    (200, json.dumps({'reqId': 'TMPAAAAAAAA-1', 'snapshotId': None}), 'no committed snapshot'),
    (401, '', 'HTTP 401'),
    (403, '', 'LEGAL'),
    (500, 'boom', 'HTTP 500'),
    (200, 'nope', 'not JSON'),
])
def test_created_refuses(status, body, phrase):
    with pytest.raises(RuntimeError, match=phrase):
        fn.created(status, body)


def test_basic_authorization_base64_encodes_the_plain_login_password():
    assert fn.basic_authorization(bytearray(b'admin:secret')) == 'Basic YWRtaW46c2VjcmV0'


def test_rg_base_is_the_validated_base_url():
    assert fn.rg_base(' http://localhost:64967/ ') == 'http://localhost:64967'
    with pytest.raises(ValueError, match='rg-base-url'):
        fn.rg_base('localhost:64967')


# ---------------------------------------------------------------------------------------------------
# the chain

class InMemoryRg:
    """RG's two create calls, reduced to the rules the chain depends on: the first only on a project that owns no
    snapshot; a next one only against the newest committed snapshot. Every create commits a new snapshot."""

    def __init__(self, code='TMPAAAAAAAA'):
        self.code = code
        self.snapshots = []
        self.contents = []

    def first(self, body):
        if self.snapshots:
            raise RuntimeError('RG refused the requirement: 04.876.020 already owns snapshots')
        return self._commit(body)

    def next(self, body):
        if not self.snapshots or body['snapshotId'] != self.snapshots[-1]:
            raise RuntimeError('RG refused the requirement: snapshot ' + str(body['snapshotId']) + ' is not the newest')
        return self._commit(body)

    def _commit(self, body):
        self.contents.append(body['content'])
        self.snapshots.append(100 + len(self.snapshots))
        return self.code + '-' + str(len(self.contents)), self.snapshots[-1]


def three():
    return fn.parse_requirements(answer(
        dict(REQ, content='Derby shall build with Apache Ant.'),
        dict(REQ, content='Derby shall run its tests with JUnit.'),
        dict(REQ, content='Derby shall document every build target.')))


def test_store_all_chains_each_requirement_onto_the_snapshot_the_previous_one_committed():
    rg = InMemoryRg()

    ids = fn.store_all(three(), rg.first, rg.next)

    assert ids == ['TMPAAAAAAAA-1', 'TMPAAAAAAAA-2', 'TMPAAAAAAAA-3']
    assert rg.contents == ['Derby shall build with Apache Ant.', 'Derby shall run its tests with JUnit.',
                           'Derby shall document every build target.']
    assert rg.snapshots == [100, 101, 102]


def test_store_all_stores_nothing_into_a_project_that_already_owns_a_snapshot():
    rg = InMemoryRg()
    rg.snapshots.append(99)

    with pytest.raises(RuntimeError, match='04.876.020'):
        fn.store_all(three(), rg.first, rg.next)
    assert rg.contents == []


def test_store_all_names_what_was_already_stored_when_a_later_one_fails():
    rg = InMemoryRg()

    def next_that_fails_on_the_third(body):
        if len(rg.contents) == 2:
            raise RuntimeError('RG refused the requirement: 012.330 ERROR')
        return rg.next(body)

    with pytest.raises(RuntimeError, match='already stored: TMPAAAAAAAA-1, TMPAAAAAAAA-2'):
        fn.store_all(three(), rg.first, next_that_fails_on_the_third)


# ---------------------------------------------------------------------------------------------------
# the wire - post_json against a loopback server that answers every POST with what it received

class JsonEchoHandler(http.server.BaseHTTPRequestHandler):
    """Echoes each POST as JSON, with the body parsed. The status is 200, or <code> for a path /status/<code>."""

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length') or 0)).decode('utf-8')
        status = int(self.path.rsplit('/', 1)[1]) if self.path.startswith('/status/') else 200
        echoed = json.dumps({
            'method': self.command,
            'path': self.path,
            'contentType': self.headers.get('Content-Type'),
            'authorization': self.headers.get('Authorization'),
            'json': json.loads(body),
        }).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(echoed)))
        self.end_headers()
        self.wfile.write(echoed)

    def log_message(self, fmt, *args):
        pass


@pytest.fixture
def echo_server():
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), JsonEchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield 'http://127.0.0.1:' + str(server.server_address[1])
    server.shutdown()
    server.server_close()


def test_post_json_sends_the_body_as_json(echo_server):
    req = fn.parse_requirements(answer(REQ))[0]

    status, text = fn.post_json(fn.next_url(echo_server, 'TMPAAAAAAAA'), fn.next_body(req, 10), 'Basic x', 5)
    echoed = json.loads(text)

    assert status == 200
    assert echoed['path'] == '/rest/v1/rg/TMPAAAAAAAA/requirements/manual'
    assert echoed['contentType'].startswith('application/json')
    assert echoed['authorization'] == 'Basic x'
    assert echoed['json'] == fn.next_body(req, 10)


def test_post_json_returns_an_error_status_instead_of_raising(echo_server):
    status, _ = fn.post_json(echo_server + '/status/403', {'content': 'a b c'}, 'Basic x', 5)

    assert status == 403
