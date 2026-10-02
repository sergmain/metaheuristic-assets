# mh.asset.mh-api-probe_1.0 - call ONE GET endpoint of the MH REST API with a credential from the Vault,
# and hand back its JSON answer. A probe: it proves that a DAHF flow reaches an MH REST endpoint,
# authenticated, end to end.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# mh-api-probe/functions/fn-mh-api-probe/mh-function.yaml.
#
# REUSABLE BY CONSTRUCTION. Nothing about a particular run is written into this Function or into the .mhsc
# that calls it, and every variable is named by a meta, never hard-coded:
#
#   mh-base-url   an INPUT  - the MH dispatcher to call, e.g. http://localhost:64967
#   production    an INPUT, nullable - exactly 'true' asks the endpoint for its production view
#                 (?production=true); every other value, null included, for the synthetic one
#   result        an OUTPUT - the endpoint's JSON answer, exactly as received
#
# and one meta that names no variable:
#
#   api-path      the endpoint, e.g. /rest/v1/dispatcher/meta-storage/meta-tables
#
# THE CREDENTIAL comes from the vault, never from a variable: mh-function.yaml declares api keyCode
# MH_API_AUTH, the PLAIN login:password of an MH account whose role the endpoint admits. MH's REST API takes
# HTTP Basic, so the pair is base64-encoded here. It is never printed, and the buffer it arrived in is zeroed
# on the way out.
#
# Any answer but HTTP 200 with a JSON body fails the Task, naming the status and an excerpt of the body.
#
# The core below is what mh-api-probe/tests exercises: pure functions, plus http_get and run, which work
# against a loopback HTTP server the tests start themselves. main() is the boundary and is not unit-tested,
# per MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md 5.5-5.6.

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from mh_secret_client import exchange, extract_secret_fields, zero

FUNCTION_CODE = 'mh.asset.mh-api-probe_1.0'

# One request. With the 10s handshake window this is the Function's worst case, which the process timeout
# in the .mhsc must exceed.
HTTP_TIMEOUT_SEC = 10

ARTIFACTS_DIR = 'artifacts'


# ---------------------------------------------------------------------------------------------------
# METAS and VARIABLES - task.metas is a LIST of maps, first hit wins, and every variable is found through the
# meta that names it (the lookup of mh_rg_temp_project.py).

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
    """Exactly 'true' (surrounding whitespace aside) is production; every other value, None included, is not."""
    return value is not None and value.strip() == 'true'


def probe_url(base_url, api_path, production):
    """base + path + ?production=true|false. The base must be http(s); the path must start with '/'."""
    base = (base_url or '').strip().rstrip('/')
    if not (base.startswith('http://') or base.startswith('https://')):
        raise ValueError("input mh-base-url must be an http(s) URL, got '" + base + "'")
    path = (api_path or '').strip()
    if not path.startswith('/'):
        raise ValueError("meta api-path must start with '/', got '" + path + "'")
    return base + path + '?' + urllib.parse.urlencode({'production': 'true' if production else 'false'})


def basic_authorization(credential):
    """The Authorization header for the vault's plain login:password (RFC 7617).

    The vault holds the pair as typed - NOT base64 - so the encoding happens here. A trailing line break is
    dropped: a value pasted into a form often carries one. The login is everything before the first colon;
    the password may contain colons. Nothing about the value is ever put into a message.
    """
    raw = bytes(credential).strip(b'\r\n')
    login, colon, _ = raw.partition(b':')
    if not colon or not login:
        raise ValueError('MH_API_AUTH must hold the plain login:password of an MH account - the MH REST API '
                         'authenticates with HTTP Basic - but the value handed over has '
                         + ('no colon' if not colon else 'an empty login') + ' (the value is not printed)')
    return 'Basic ' + base64.b64encode(raw).decode('ascii')


def excerpt(text, limit=300):
    """The start of a body, on one line, for an error message."""
    flat = ' '.join((text or '').split())
    return flat if len(flat) <= limit else flat[:limit] + '...'


def check_answer(status, text, url):
    """The parsed body of an HTTP 200 that is JSON; any other answer is a failure naming the status."""
    if status != 200:
        raise RuntimeError('GET ' + url + ' -> HTTP ' + str(status) + ': ' + excerpt(text))
    try:
        return json.loads(text)
    except ValueError:
        raise RuntimeError('GET ' + url + ' -> HTTP 200, but the body is not JSON: ' + excerpt(text)) from None


def summary(answer):
    """One console line about the answer's SHAPE - its keys and the sizes of its lists, no values."""
    if isinstance(answer, dict):
        sizes = {k: len(v) for k, v in answer.items() if isinstance(v, list)}
        return 'keys ' + str(sorted(answer.keys())) + ((', list sizes ' + str(sizes)) if sizes else '')
    return type(answer).__name__


def http_get(url, authorization, timeout=HTTP_TIMEOUT_SEC):
    """GET and return (status, body text). An HTTP error status is returned, not raised; no proxy is used."""
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
        raise RuntimeError('cannot reach MH at ' + url + ': ' + str(e.reason)) from None


# ---------------------------------------------------------------------------------------------------
# THE BOUNDARY

def read_text(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def write_text(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def run(task, credential):
    metas = task.get('metas') or []
    work_dir = task['workingPath']
    inputs = task.get('inputs')

    def read_input(role):
        # None for a NULLIFIED input (marked 'empty', no file) - production is declared nullable
        var = find_variable(inputs, variable_name(metas, role))
        if var.get('empty'):
            return None
        return read_text(input_path(work_dir, var))

    url = probe_url(read_input('mh-base-url'), require_meta(metas, 'api-path'), is_production(read_input('production')))
    # resolved BEFORE MH is called: a missing output declaration is a SourceCode defect
    target = output_path(work_dir, find_variable(task.get('outputs'), variable_name(metas, 'result')))
    print('GET ' + url)

    if credential is None:
        raise ValueError('no credential was handed over: mh-function.yaml declares api keyCode MH_API_AUTH, '
                         'but the params file carries no secretPort / checkCode')
    status, text = http_get(url, basic_authorization(credential))
    answer = check_answer(status, text, url)
    write_text(target, text)
    print('HTTP 200, ' + summary(answer))
    return 0


def main(argv):
    # imported here rather than at module scope: the core above must stay importable by a test that has no
    # PyYAML installed, because nothing in the core needs it
    import yaml

    print(FUNCTION_CODE)

    # the LAST positional argument is always the absolute path to the params file
    with open(argv[len(argv) - 1], 'r', encoding='utf-8') as stream:
        params = yaml.load(stream, Loader=yaml.FullLoader)

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
