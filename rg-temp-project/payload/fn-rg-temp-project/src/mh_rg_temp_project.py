# mh.asset.rg-temp-project_1.0 - create a temporary RG project through the RG REST API and report its
# code. mkdtemp, for RG.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# rg-temp-project/functions/fn-rg-temp-project/mh-function.yaml.
#
# THE ALGORITHM IS mkdtemp'S. A temporary directory is made by drawing a random name under a fixed
# prefix and attempting the create; the create itself is the uniqueness check, so nothing can take the
# name between a check and the create, and a name that turns out to be taken costs one more draw:
#
#   draw     'TMP' + 8 characters from A-Z0-9, picked by a CSPRNG. Upper case because RG stores every
#            code upper-cased; no separator because requirement ids carry the code followed by '-<n>'
#            (DRONE-2), and a hyphen inside the code would blur that boundary
#   create   POST /rest/v1/rg/projects/add - RG refuses a code that already exists
#   retry    on that refusal only, at most MAX_ATTEMPTS times. Every other refusal is final
#
# RG has no 'temporary' flag. Temporary is how the code is minted, and what the project says about
# itself - its name, and a description naming the ExecContext that minted it. Nothing here deletes it.
#
# REUSABLE BY CONSTRUCTION. Nothing about a particular run is written into this Function or into the
# .mhsc that calls it, and EVERY variable is named by a meta, never hard-coded:
#
#   rg-base-url    an INPUT  - which RG to create the project in, e.g. http://localhost:64967
#   locale         an INPUT  - the project's language, validated by RG rather than copied here
#   production     an INPUT  - 'true' creates the project; every other value is a development run
#   project-code   an OUTPUT - the code RG answered with, or 'mh.null-value' when nothing was created
#
# THE CREDENTIAL comes from the vault, never from a variable. mh-function.yaml declares api keyCode
# RG_API_KEY and the Processor hands its value over the loopback secret channel at launch. The vault
# holds the PLAIN login:password of an RG account - not base64 - and RG's REST API accepts HTTP Basic
# only, so this Function base64-encodes it into the Authorization header. It is never printed, and the
# buffer it arrived in is zeroed on the way out.
#
# 1.1: the vault entry is RG_API_AUTH, not RG_API_KEY - it holds a login:password, not an API key.
#
# The core below is what rg-temp-project/tests exercises: pure functions, plus post_form, which runs
# against a loopback HTTP server the tests start themselves. main() is the boundary and is not
# unit-tested, per MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md 5.5-5.6.

import base64
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

from mh_secret_client import exchange, extract_secret_fields, zero

FUNCTION_CODE = 'mh.asset.rg-temp-project_1.1'

# The draw: a fixed prefix, then CODE_RANDOM_LENGTH characters of CODE_ALPHABET. 11 characters in all,
# against RG's limit of 20 (LegalInfoBankService), and 36^8 = 2.8e12 codes under the prefix.
CODE_PREFIX = 'TMP'
CODE_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
CODE_RANDOM_LENGTH = 8

# mkdtemp tries up to TMP_MAX (10000) names, because a local mkdir costs nothing. Every attempt here is
# an HTTP round trip, and with 2.8e12 codes a second draw is already improbable: the loop is there for
# correctness, not for throughput.
MAX_ATTEMPTS = 3

# Per request. MAX_ATTEMPTS x HTTP_TIMEOUT_SEC plus the handshake is the Function's worst case, which the
# process timeout in the .mhsc must exceed.
HTTP_TIMEOUT_SEC = 5

CREATE_PATH = '/rest/v1/rg/projects/add'

# RG's other project calls - made only when a process names an RG pipeline: the SourceCodes a project may
# run, and the call that assigns one and marks the project ready.
SOURCE_CODES_PATH = '/rest/v1/rg/projects/{code}/source-codes'
TASK_PATH = '/rest/v1/rg/projects/{id}/task'

# RG states a taken code only in words: RgProjectService answers "Info bank with code 'X' already
# exists", LegalInfoBankService "Info bank with this code already exists". Both carry this phrase. If RG
# ever rewords them, the loop stops retrying and the run fails with RG's own message - it can never
# mistake another refusal for a collision.
EXISTS_PHRASE = 'already exists'

CREATED = 'created'
EXISTS = 'exists'

# The null value of a required variable, by the repo-wide convention: greppable, and never mistakable for
# a project code.
NULL_VALUE = 'mh.null-value'

ARTIFACTS_DIR = 'artifacts'


# ---------------------------------------------------------------------------------------------------
# METAS and VARIABLES - the lookup call-cc performs (mh_call_cc.py): task.metas is a LIST of maps, first
# hit wins, and every variable is found through the meta that names it.

def meta_value(metas, key):
    """The first value for key across the metas list, or None."""
    for meta in metas or []:
        if not isinstance(meta, dict):
            continue
        value = meta.get(key)
        if value is not None:
            return str(value)
    return None


def meta_keys(metas):
    """Every key declared across the metas list, sorted. For error messages, so a typo names itself."""
    return sorted({key for meta in metas or [] if isinstance(meta, dict) for key in meta})


def require_meta(metas, key):
    """A meta with no default: absent or blank is a defect in the SourceCode, never a runtime state."""
    value = meta_value(metas, key)
    if value is None or not value.strip():
        raise ValueError("meta '" + key + "' is required and was not declared. Declared metas: "
                         + str(meta_keys(metas)))
    return value.strip()


def variable_name(metas, logical_name):
    """The actual Variable name bound to a logical role, via meta 'variable-for-<logical_name>'."""
    return require_meta(metas, 'variable-for-' + logical_name)


def find_variable(variables, name):
    """The declared variable with this name, or a failure that lists what WAS declared."""
    for var in variables or []:
        if isinstance(var, dict) and var.get('name') == name:
            return var
    declared = [v.get('name') for v in variables or [] if isinstance(v, dict)]
    raise ValueError("variable '" + name + "' is not declared in the task params. Declared: " + str(declared))


def input_path(working_path, var):
    """Where the Processor put an input variable: {workingPath}/{dataType}/{id}."""
    return os.path.join(working_path, str(var.get('dataType') or 'variable'), str(var['id']))


def output_path(working_path, var):
    """Where an output variable is expected: {workingPath}/artifacts/{id}."""
    return os.path.join(working_path, ARTIFACTS_DIR, str(var['id']))


# ---------------------------------------------------------------------------------------------------
# THE CORE

def is_production(value):
    """Production is the literal 'true' and nothing else.

    'mh.null-value', an empty string, 'True', a typo - every other value is a development run. A project
    created by mistake stays in RG until someone deletes it, while a development run that should have
    been production costs one re-run; so the expensive outcome is the one that needs a deliberate act.
    """
    return value is not None and value.strip() == 'true'


def random_code(choose, prefix=CODE_PREFIX, alphabet=CODE_ALPHABET, length=CODE_RANDOM_LENGTH):
    """One candidate code: prefix, then length characters, each picked by choose(alphabet).

    choose is a parameter so that the draw production makes - secrets.choice - and a draw a test can
    predict go through the same function.
    """
    return prefix + ''.join(choose(alphabet) for _ in range(length))


def create_url(base_url):
    """The create endpoint under base_url.

    The input arrives from a Variable, so surrounding whitespace and a trailing slash are dropped.
    Anything that is not an absolute http(s) url is refused here, before a credential is sent anywhere.
    """
    url = (base_url or '').strip().rstrip('/')
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError("rg-base-url must be an absolute http(s) url such as http://localhost:64967, got '"
                         + url + "'")
    return url + CREATE_PATH


def rg_base(base_url):
    """The RG base url itself, validated exactly as create_url validates it - for the calls that are not the create."""
    return create_url(base_url)[:-len(CREATE_PATH)]


def basic_authorization(credential):
    """The Authorization header for the vault's plain login:password (RFC 7617).

    The vault holds the pair as typed - NOT base64 - so the encoding happens here. A trailing line break
    is dropped: a value pasted into a form often carries one, and no login or password ends in it. The
    login is everything before the first colon; the password may contain colons. Nothing about the value
    is ever put into a message.

    Python cannot build an HTTP header without immutable copies of the credential. What can be zeroed -
    the bytearray it arrived in - is zeroed by main().
    """
    raw = bytes(credential).strip(b'\r\n')
    login, colon, _ = raw.partition(b':')
    if not colon or not login:
        raise ValueError('RG_API_AUTH must hold the plain login:password of an RG account - RG authenticates '
                         'with HTTP Basic only - but the value handed over has '
                         + ('no colon' if not colon else 'an empty login') + ' (the value is not printed)')
    return 'Basic ' + base64.b64encode(raw).decode('ascii')


def project_name(code):
    return 'Temporary project ' + code


def project_description(exec_context_id):
    """Names the run that minted the project, so a temporary project can be traced back - and retired -
    without asking anyone."""
    return 'Temporary project created by ' + FUNCTION_CODE + ' in ExecContext #' + str(exec_context_id)


def form_body(code, locale, exec_context_id, description=None, max_depth=None):
    """The request parameters RgProjectController.createProject reads, form-encoded.

    maxDepth is left out: absent means RG's default, and a temporary project has no reason to differ.

    Unless the process says otherwise: description replaces the minted description when given, and max_depth
    is sent as maxDepth when given - a project that is to receive hand-authored requirements needs 1
    (RgFirstManualRequirementService: its genesis run must mint exactly one requirement).

    Correction: RG accepts maxDepth only in [2, 6] (RgConsts) and refuses anything else (03.877.010); a MANUAL
    genesis runs at depth 1 whatever the project holds (RgExecTxService 827.145), so requirements need no
    particular depth. max_depth stays for a caller that wants a deeper decomposition bound.
    """
    fields = {
        'name': project_name(code),
        'infoBank': code,
        'locale': locale,
        'description': description if description else project_description(exec_context_id),
    }
    if max_depth is not None:
        fields['maxDepth'] = str(max_depth)
    return urllib.parse.urlencode(fields).encode('utf-8')


def excerpt(text, limit=300):
    """The head of a response body, for a failure message - a login page is kilobytes of HTML."""
    text = text or ''
    return text if len(text) <= limit else text[:limit] + '...'


def classify(status, text):
    """RG's answer to one create, as (CREATED, code) or (EXISTS, None); anything else raises.

    A taken code is the only refusal that means 'draw again'. Everything else - a rejected credential, a
    missing role, an unsupported locale, a body that is not RG's - is final, and is raised with RG's own
    words, so the run's console says what RG said.
    """
    if status == 401:
        raise RuntimeError('RG rejected the credential (HTTP 401) - RG_API_AUTH must be the plain '
                           'login:password of an RG account')
    if status == 403:
        raise RuntimeError('RG refused the request (HTTP 403) - the account in RG_API_AUTH needs the role '
                           'ADMIN or LEGAL_ADMIN')
    if status != 200:
        raise RuntimeError('RG answered HTTP ' + str(status) + ': ' + excerpt(text))
    try:
        answer = json.loads(text)
    except ValueError:
        raise RuntimeError('RG answered HTTP 200 with a body that is not JSON: ' + excerpt(text)) from None
    if not isinstance(answer, dict):
        raise RuntimeError('RG answered HTTP 200 with JSON that is not an object: ' + excerpt(text))
    errors = [str(m) for m in (answer.get('errorMessages') or [])]
    if errors:
        if any(EXISTS_PHRASE in m for m in errors):
            return EXISTS, None
        raise RuntimeError('RG refused to create the project: ' + '; '.join(errors))
    project = answer.get('project')
    code = project.get('infoBank') if isinstance(project, dict) else None
    if not code:
        raise RuntimeError('RG answered without an error and without a project code: ' + excerpt(text))
    return CREATED, str(code)


def should_create(production, create_in_development):
    """Whether this run creates the project for real. A production run always does; a development run does
    only when the process declares meta create-in-development = "true" - a workflow whose temporary project is
    itself the scratch space it works in, and so has nothing to protect by not creating it."""
    return is_production(production) or (create_in_development or '').strip() == 'true'


def optional_text(value):
    """The text of an optional input, or None when it is absent, blank or 'mh.null-value'."""
    text = (value or '').strip()
    return None if not text or text == NULL_VALUE else text


def parse_max_depth(value):
    """meta max-depth as a positive whole number, or None when the process does not declare it."""
    if value is None or not str(value).strip():
        return None
    try:
        depth = int(str(value).strip())
    except ValueError:
        raise ValueError("meta max-depth must be a whole number, got '" + str(value) + "'") from None
    if depth < 1:
        raise ValueError('meta max-depth must be at least 1, got ' + str(depth))
    return depth


def project_id(text):
    """The numeric id of the project an add answered with - RG's other project calls address it by id."""
    try:
        answer = json.loads(text)
    except ValueError:
        answer = None
    project = answer.get('project') if isinstance(answer, dict) else None
    pid = project.get('id') if isinstance(project, dict) else None
    if pid is None:
        raise RuntimeError('RG created the project but its answer carries no project id: ' + excerpt(text))
    return int(pid)


def rg_json(status, text, what):
    """RG's answer to a call whose only success condition is 'no error': the parsed JSON object - or a failure
    that says which call it was and what RG answered."""
    if status == 401:
        raise RuntimeError(what + ': RG rejected the credential (HTTP 401) - RG_API_AUTH must be the plain '
                           'login:password of an RG account')
    if status == 403:
        raise RuntimeError(what + ': RG refused the request (HTTP 403) - the account in RG_API_AUTH needs the '
                           'role ADMIN or LEGAL_ADMIN')
    if status != 200:
        raise RuntimeError(what + ': RG answered HTTP ' + str(status) + ': ' + excerpt(text))
    try:
        answer = json.loads(text)
    except ValueError:
        raise RuntimeError(what + ': RG answered HTTP 200 with a body that is not JSON: ' + excerpt(text)) from None
    if not isinstance(answer, dict):
        raise RuntimeError(what + ': RG answered with JSON that is not an object: ' + excerpt(text))
    errors = [str(m) for m in (answer.get('errorMessages') or [])]
    if errors:
        raise RuntimeError(what + ': ' + '; '.join(errors))
    return answer


def source_code_id_for(uid, answer):
    """The id of the SourceCode named uid in RG's /source-codes answer - or a failure listing what RG does offer."""
    options = [o for o in (answer.get('sourceCodes') or []) if isinstance(o, dict)]
    for option in options:
        if option.get('uid') == uid:
            return int(option['sourceCodeId'])
    raise RuntimeError("RG offers this project no SourceCode '" + uid + "'; it offers: "
                       + str(sorted(str(o.get('uid')) for o in options)))


def source_codes_url(base, code):
    return base + SOURCE_CODES_PATH.format(code=urllib.parse.quote(code))


def task_url(base, pid):
    return base + TASK_PATH.format(id=pid)


def task_body(source_code_id):
    """Assign the pipeline and mark the project ready in one call. isReady must be sent: RG defaults it to false."""
    return urllib.parse.urlencode({'sourceCodeId': str(source_code_id), 'isReady': 'true'}).encode('utf-8')


def create_temp_project(create, next_code, max_attempts=MAX_ATTEMPTS):
    """mkdtemp's loop. Returns the code of the project that was created.

    create(code) answers (CREATED, code) or (EXISTS, None) and raises on anything final; next_code()
    draws a candidate. Only EXISTS leads to another draw - an exception from create is never caught here.
    """
    if max_attempts < 1:
        raise ValueError('max_attempts must be greater than 0, got ' + str(max_attempts))
    for _ in range(max_attempts):
        outcome, code = create(next_code())
        if outcome == CREATED:
            return code
        if outcome != EXISTS:
            raise ValueError('create answered an unknown outcome: ' + repr(outcome))
    raise RuntimeError('no free project code after ' + str(max_attempts) + ' attempts - every code drawn '
                       'was already taken')


def post_form(url, body, authorization, timeout=HTTP_TIMEOUT_SEC):
    """POST a form and return (status, body text).

    An HTTP error status is RETURNED, not raised - which status it was is exactly what classify() needs.
    Only a server that cannot be reached raises.

    No proxy, deliberately: urllib would otherwise pick one up from the OS (on Windows, from the
    registry), and whether a desktop proxy setting should sit between a Function and RG is not a decision
    this Function can see being made.
    """
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, data=body, method='POST', headers={
        'Authorization': authorization,
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Accept': 'application/json',
    })
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='replace')
    except urllib.error.URLError as e:
        raise RuntimeError('cannot reach RG at ' + url + ': ' + str(e.reason)) from None


def http_get(url, authorization, timeout=HTTP_TIMEOUT_SEC):
    """GET and return (status, body text), with post_form's rules: an HTTP error status is returned, not raised,
    and no proxy is used."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, method='GET', headers={
        'Authorization': authorization,
        'Accept': 'application/json',
    })
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='replace')
    except urllib.error.URLError as e:
        raise RuntimeError('cannot reach RG at ' + url + ': ' + str(e.reason)) from None


# ---------------------------------------------------------------------------------------------------
# THE BOUNDARY

def read_text(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def write_text(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def read_optional_input(metas, work_dir, inputs, role):
    """The text of the Variable an OPTIONAL role is bound to, or None when the process binds none."""
    name = meta_value(metas, 'variable-for-' + role)
    if name is None or not name.strip():
        return None
    return read_text(input_path(work_dir, find_variable(inputs, name.strip())))


def run(task, credential):
    metas = task.get('metas') or []
    work_dir = task['workingPath']
    inputs = task.get('inputs')

    def read_input(role):
        return read_text(input_path(work_dir, find_variable(inputs, variable_name(metas, role))))

    base = rg_base(read_input('rg-base-url'))
    url = base + CREATE_PATH
    locale = read_input('locale').strip()
    production = read_input('production')
    # optional roles and metas - a process that declares none of them gets exactly the behaviour described above
    description = optional_text(read_optional_input(metas, work_dir, inputs, 'description'))
    pipeline_uid = optional_text(read_optional_input(metas, work_dir, inputs, 'rg-pipeline-uid'))
    max_depth = parse_max_depth(meta_value(metas, 'max-depth'))
    create_in_development = meta_value(metas, 'create-in-development')
    # resolved BEFORE RG is called: a missing output declaration is a SourceCode defect, and finding it
    # after the project exists would leave a project whose code nobody was told
    target = output_path(work_dir, find_variable(task.get('outputs'), variable_name(metas, 'project-code')))
    print('rg: ' + url + ', locale: ' + locale + ', production: ' + repr(production.strip()))

    if not locale:
        raise ValueError('input locale is empty - RG requires a language for every project')
    if credential is None:
        raise ValueError('no credential was handed over: mh-function.yaml declares api keyCode RG_API_AUTH, '
                         'but the params file carries no secretPort / checkCode')
    authorization = basic_authorization(credential)

    if not should_create(production, create_in_development):
        write_text(target, NULL_VALUE)
        print('development run: inputs and credential checked, nothing created in RG, projectCode='
              + NULL_VALUE)
        return 0

    exec_context_id = task['execContextId']
    created_ids = []

    def create(code):
        status, text = post_form(url, form_body(code, locale, exec_context_id, description, max_depth), authorization)
        print('POST ' + url + ' infoBank=' + code + ' -> HTTP ' + str(status))
        outcome = classify(status, text)
        if outcome[0] == CREATED:
            created_ids.append(project_id(text))
        return outcome

    code = create_temp_project(create, lambda: random_code(secrets.choice))
    if pipeline_uid:
        # the project runs this RG pipeline and is ready - the precondition for storing requirements in it
        status, text = http_get(source_codes_url(base, code), authorization)
        source_code_id = source_code_id_for(pipeline_uid, rg_json(status, text, 'list the SourceCodes of ' + code))
        status, text = post_form(task_url(base, created_ids[-1]), task_body(source_code_id), authorization)
        rg_json(status, text, 'assign SourceCode ' + pipeline_uid + ' to ' + code)
        print('project ' + code + ' runs ' + pipeline_uid + ' (SourceCode #' + str(source_code_id) + ') and is ready')
    write_text(target, code)
    print('created temporary RG project ' + code)
    return 0


def main(argv):
    # imported here rather than at module scope: the core above must stay importable by a test that has
    # no PyYAML installed, because nothing in the core needs it
    import yaml

    print(FUNCTION_CODE)
    print('Cwd: ', os.getcwd())
    print('Script: ', os.path.abspath(__file__))

    # the LAST positional argument is always the absolute path to the params file
    with open(argv[len(argv) - 1], 'r', encoding='utf-8') as stream:
        params = yaml.load(stream, Loader=yaml.FullLoader)

    # FIRST, before anything that can take time: the Processor's accept() waits 10 seconds for this
    # connection (VAULT-SECRET-HANDOFF-PROTOCOL.md), in a development run as much as in a production one
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
