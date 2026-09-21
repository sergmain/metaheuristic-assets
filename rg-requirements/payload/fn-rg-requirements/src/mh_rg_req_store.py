# mh.asset.rg-req-store_1.0 - store the requirements CC produced in an RG project.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# rg-requirements/functions/fn-rg-req-store/mh-function.yaml.
#
# roles - every Variable is named by a meta, never hard-coded:
#   rg-base-url    INPUT  - the RG (dispatcher) base url, e.g. http://localhost:64967
#   project-code   INPUT  - the project to store into. It must run an RG genesis pipeline, be ready and have
#                           maxDepth 1 - what mh.asset.rg-temp-project does with metas max-depth = "1" and
#                           variable-for-rg-pipeline-uid
#                           Correction: not maxDepth - RG refuses a maxDepth below 2, and a MANUAL genesis runs at
#                           depth 1 on its own (RgExecTxService 827.145). The pipeline and readiness are what count.
#   cc-result      INPUT  - CC's answer: a JSON array of {name, content, rationale}
#   req-ids        OUTPUT - the ids RG gave the stored requirements, one per line, in the answer's order
#
# THE CREDENTIAL is the vault entry RG_API_AUTH - the plain login:password of an RG account - handed over on the
# Processor's loopback secret channel (java/legal/docs/security/SECURITY-MODEL-VAULT-KEY-DELIVERY.md).
#
# HOW RG TAKES THEM. A project that owns no snapshot accepts exactly one call: requirements/manual/first. It
# carries requirement #1 into the project's one-shot genesis run, waits for that run to commit, and answers with
# the snapshot it committed. Every further requirement goes to requirements/manual against a COMMITTED snapshot -
# the one the previous call sealed, which RG answers as snapshotId - so the requirements are chained, each onto
# the snapshot the one before it produced. Nothing is guessed from the tree.
#
# EVERYTHING IS CHECKED BEFORE THE FIRST WRITE. The first call spends the project's genesis and cannot be taken
# back, so a malformed answer - not an array, an empty one, a requirement under RG's 3-word minimum, a missing
# rationale - fails the Task before RG is touched.

import base64
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from mh_secret_client import exchange, extract_secret_fields, zero
from mh_task_io import load_params, output_role, read_role, write_text

FUNCTION_CODE = 'mh.asset.rg-req-store_1.0'

# RgManualRequirementContentUtils.MIN_CONTENT_WORDS - checked here as well, so an answer RG would refuse after
# the genesis has fired is refused before it.
MIN_CONTENT_WORDS = 3

# requirements/manual/first answers only once the genesis run has committed; each later call is one transaction.
FIRST_TIMEOUT_SEC = 900
NEXT_TIMEOUT_SEC = 120

FIRST_PATH = '/rest/v1/rg/{code}/requirements/manual/first'
NEXT_PATH = '/rest/v1/rg/{code}/requirements/manual'

# A model sometimes wraps JSON in a markdown fence. That, and only that, is unwrapped.
FENCE = re.compile(r'^```[A-Za-z]*\s*\n(.*)\n```$', re.DOTALL)


def excerpt(text, limit=300):
    text = text or ''
    return text if len(text) <= limit else text[:limit] + '...'


def parse_requirements(cc_result):
    """CC's answer as a list of {name, content, rationale} - or a failure listing every problem at once."""
    text = (cc_result or '').strip()
    fenced = FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError('CC answered something that is not JSON: ' + excerpt(text)) from None
    if not isinstance(data, list) or not data:
        raise ValueError('CC answered no requirements - expected a non-empty JSON array, got: ' + excerpt(text))
    problems = []
    requirements = []
    for i, item in enumerate(data, 1):
        label = '#' + str(i)
        if not isinstance(item, dict):
            problems.append(label + ' is not an object')
            continue
        content = item.get('content')
        rationale = item.get('rationale')
        name = item.get('name')
        item_problems = []
        if not isinstance(content, str) or len(content.split()) < MIN_CONTENT_WORDS:
            item_problems.append(label + ' content must be text of at least ' + str(MIN_CONTENT_WORDS) + ' words')
        if not isinstance(rationale, str) or not rationale.strip():
            item_problems.append(label + ' has no rationale')
        if name is not None and not isinstance(name, str):
            item_problems.append(label + ' name is not text')
        if item_problems:
            problems.extend(item_problems)
        else:
            requirements.append({
                'name': name.strip() if isinstance(name, str) and name.strip() else None,
                'content': content.strip(),
                'rationale': rationale.strip(),
            })
    if problems:
        raise ValueError('CC answer refused before anything was stored: ' + '; '.join(problems))
    return requirements


def first_body(requirement):
    """The body of requirements/manual/first: no parent and no snapshot - the project has neither yet."""
    return {'content': requirement['content'], 'name': requirement['name'], 'rationale': requirement['rationale']}


def next_body(requirement, snapshot_id):
    """The body of requirements/manual. SECTION with no parent is top-level, like the first requirement: RG
    requires parentReqId only for parentKind REQ."""
    return {
        'content': requirement['content'],
        'name': requirement['name'],
        'parentReqId': '',
        'parentKind': 'SECTION',
        'rationale': requirement['rationale'],
        'snapshotId': snapshot_id,
    }


def first_url(base, code):
    return base + FIRST_PATH.format(code=urllib.parse.quote(code))


def next_url(base, code):
    return base + NEXT_PATH.format(code=urllib.parse.quote(code))


def created(status, text):
    """RG's answer to one create: (reqId, committed snapshotId) - or a failure carrying RG's own words."""
    if status == 401:
        raise RuntimeError('RG rejected the credential (HTTP 401) - RG_API_AUTH must be the plain login:password '
                           'of an RG account')
    if status == 403:
        raise RuntimeError('RG refused the request (HTTP 403) - the account in RG_API_AUTH needs the role ADMIN, '
                           'LEGAL or LEGAL_ADMIN')
    if status != 200:
        raise RuntimeError('RG answered HTTP ' + str(status) + ': ' + excerpt(text))
    try:
        answer = json.loads(text)
    except ValueError:
        raise RuntimeError('RG answered HTTP 200 with a body that is not JSON: ' + excerpt(text)) from None
    if not isinstance(answer, dict):
        raise RuntimeError('RG answered with JSON that is not an object: ' + excerpt(text))
    errors = [str(m) for m in (answer.get('errorMessages') or [])]
    if errors:
        raise RuntimeError('RG refused the requirement: ' + '; '.join(errors))
    req_id = answer.get('reqId')
    if not isinstance(req_id, str) or not req_id.strip():
        raise RuntimeError('RG answered with no requirement id: ' + excerpt(text))
    snapshot_id = answer.get('snapshotId')
    if snapshot_id is None:
        raise RuntimeError('RG stored ' + req_id.strip() + ' but reported no committed snapshot - the next '
                           'requirement would have none to name')
    return req_id.strip(), int(snapshot_id)


def store_all(requirements, post_first, post_next):
    """The chain: #1 through post_first (the genesis), each next one onto the snapshot the previous call committed.
    post_first(body) and post_next(body) answer (reqId, snapshotId). Returns the requirement ids in order."""
    if not requirements:
        raise ValueError('nothing to store')
    req_id, snapshot_id = post_first(first_body(requirements[0]))
    ids = [req_id]
    for requirement in requirements[1:]:
        try:
            req_id, snapshot_id = post_next(next_body(requirement, snapshot_id))
        except RuntimeError as e:
            raise RuntimeError(str(e) + ' - already stored: ' + ', '.join(ids)) from None
        ids.append(req_id)
    return ids


def rg_base(base_url):
    """The RG base url: surrounding whitespace and a trailing slash dropped, anything not absolute http(s) refused
    before a credential is sent anywhere."""
    url = (base_url or '').strip().rstrip('/')
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError("rg-base-url must be an absolute http(s) url such as http://localhost:64967, got '"
                         + url + "'")
    return url


def basic_authorization(credential):
    """The Authorization header for the vault's plain login:password (RFC 7617). The value is never printed."""
    raw = bytes(credential).strip(b'\r\n')
    login, colon, _ = raw.partition(b':')
    if not colon or not login:
        raise ValueError('RG_API_AUTH must hold the plain login:password of an RG account - RG authenticates '
                         'with HTTP Basic only - but the value handed over has '
                         + ('no colon' if not colon else 'an empty login') + ' (the value is not printed)')
    return 'Basic ' + base64.b64encode(raw).decode('ascii')


def post_json(url, payload, authorization, timeout):
    """POST a JSON body and return (status, body text). An HTTP error status is RETURNED - which one it was is what
    created() needs - and only an unreachable server raises. No proxy, as in rg-temp-project."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), method='POST', headers={
        'Authorization': authorization,
        'Content-Type': 'application/json; charset=UTF-8',
        'Accept': 'application/json',
    })
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='replace')
    except urllib.error.URLError as e:
        raise RuntimeError('cannot reach RG at ' + url + ': ' + str(e.reason)) from None


def run(task, credential):
    base = rg_base(read_role(task, 'rg-base-url'))
    code = (read_role(task, 'project-code') or '').strip()
    requirements = parse_requirements(read_role(task, 'cc-result'))
    # resolved BEFORE RG is called: a missing output declaration found after the genesis would leave stored
    # requirements whose ids nobody was told
    target = output_role(task, 'req-ids')
    if not code:
        raise ValueError('input project-code is empty - there is no project to store into')
    if credential is None:
        raise ValueError('no credential was handed over: mh-function.yaml declares api keyCode RG_API_AUTH, '
                         'but the params file carries no secretPort / checkCode')
    authorization = basic_authorization(credential)
    print('storing ' + str(len(requirements)) + ' requirement(s) into ' + code)

    def post_first(body):
        status, text = post_json(first_url(base, code), body, authorization, FIRST_TIMEOUT_SEC)
        print('POST requirements/manual/first -> HTTP ' + str(status))
        return created(status, text)

    def post_next(body):
        status, text = post_json(next_url(base, code), body, authorization, NEXT_TIMEOUT_SEC)
        print('POST requirements/manual onto snapshot ' + str(body['snapshotId']) + ' -> HTTP ' + str(status))
        return created(status, text)

    ids = store_all(requirements, post_first, post_next)
    write_text(target, '\n'.join(ids))
    print('stored: ' + ', '.join(ids))
    return 0


def main(argv):
    print(FUNCTION_CODE)
    params = load_params(argv)
    # FIRST, before anything that can take time: the Processor's accept() waits 10 seconds for this connection
    port, check_code = extract_secret_fields(params)
    try:
        credential = exchange(port, check_code) if port is not None else None
    except OSError as e:
        print('FAILED: the secret handoff did not complete: ' + str(e))
        return 1
    try:
        return run(params['task'], credential)
    except (ValueError, RuntimeError, OSError) as e:
        print('FAILED: ' + str(e))
        return 1
    finally:
        if credential is not None:
            zero(credential)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
