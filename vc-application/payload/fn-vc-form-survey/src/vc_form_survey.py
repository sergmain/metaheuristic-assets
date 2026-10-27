# mh.asset.vc-form-survey-<fund>_1.0 - sign in to a VC fund's application site and survey its application
# form: every input field the form defines, and the global input Variables an apply flow declares for them.
#
# This file is NOT part of any bundle. It is reached only through the git block of a vc-application
# Function descriptor (vc-application/functions/fn-vc-form-survey-<fund>/mh-function.yaml).
#
# ONE PAYLOAD SERVES EVERY FUND. What differs per fund is:
#   - the adapter module vc_fund_<fund>.py, registered in ADAPTERS: how to sign in, what a survey may send,
#     where the form's state is - and, optionally, its own extract_fields when the generic one below does
#     not fit that fund's page
#   - the Function descriptor, whose api.keyCode names the fund's Vault entry (VC_YC_AUTH for YC): a
#     descriptor carries exactly one key, so a fund is a descriptor
#   - the wrapper .mhsc: def fund, def survey_fn, over the shared vc-form-survey.mhscp
#
# A SURVEY ONLY READS. What it may send is decided per fund by the adapter's may_send, asked by the
# session (vc_http.py) before every request and every redirect. A survey writes nothing durable in either
# mode; production is read and reported, and changes nothing.
#
# REUSABLE BY CONSTRUCTION. Every variable is named by a meta, never hard-coded:
#   fund                          meta    the adapter, e.g. yc
#   variable-for-form-url         INPUT   the application's url
#   variable-for-production       INPUT   nullable; reported only
#   variable-for-form-fields      OUTPUT  the field inventory, JSON
#   variable-for-apply-variables  OUTPUT  the variables { } block of the apply flow, one input per field
#
# THE CREDENTIAL comes from the Vault, never from a Variable: the Processor hands the fund's entry over the
# loopback secret channel (mh_secret_client.py). It holds the plain login:password of the fund account; the
# password may contain colons. It is never printed, and the buffer it arrived in is zeroed on the way out.
#
# NO APPLICANT CONTENT IS COPIED OUT. The inventory carries what DEFINES a field - its key, label, type,
# options, limits, whether it is required - and the shape of the page's props with every other string
# replaced by its length (skeleton). What the applicant typed is not in either output.
#
# The core below is what vc-application/tests exercises: pure functions. main() is the boundary and is not
# unit-tested, per MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md 5.5-5.6.

import importlib
import json
import os
import re
import sys

FUNCTION_TYPE = 'mh.asset.vc-form-survey'

# fund -> adapter module, a sibling of this file
ADAPTERS = {
    'yc': 'vc_fund_yc',
}

ARTIFACTS_DIR = 'artifacts'

# What marks a dict as a field definition, and what of it is read. Keys are matched exactly.
LABEL_KEYS = ('label', 'question', 'prompt', 'title')
IDENT_KEYS = ('name', 'key', 'field', 'attribute', 'slug', 'id')
TYPE_KEYS = ('type', 'kind', 'input_type', 'inputType', 'field_type', 'fieldType', 'component', 'format')
REQUIRED_KEYS = ('required', 'is_required', 'isRequired')
OPTIONAL_KEYS = ('optional', 'is_optional', 'isOptional')
OPTION_KEYS = ('options', 'choices')
LIMIT_KEYS = ('max_length', 'maxLength', 'maxlength', 'min_length', 'minLength', 'word_limit', 'wordLimit',
              'max_words', 'maxWords', 'char_limit', 'charLimit', 'limit', 'min', 'max', 'max_files', 'maxFiles')
HELP_KEYS = ('placeholder', 'hint', 'help', 'help_text', 'helpText', 'description_hint')

IDENTIFIER = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.\-\[\]]{0,79}$')

LABEL_MAX = 300
SKELETON_TEXT_MAX = 160
SKELETON_MAX_DEPTH = 14
SKELETON_LIST_ITEMS = 3


# ---------------------------------------------------------------------------------------------------
# METAS and VARIABLES - the lookup every asset Function performs (mh_rg_temp_project.py)

def meta_value(metas, key):
    for meta in metas or []:
        if isinstance(meta, dict) and meta.get(key) is not None:
            return str(meta.get(key))
    return None


def meta_keys(metas):
    return sorted({key for meta in metas or [] if isinstance(meta, dict) for key in meta})


def require_meta(metas, key):
    value = meta_value(metas, key)
    if value is None or not value.strip():
        raise ValueError("meta '" + key + "' is required and was not declared. Declared metas: " + str(meta_keys(metas)))
    return value.strip()


def find_variable(variables, name):
    for var in variables or []:
        if isinstance(var, dict) and var.get('name') == name:
            return var
    declared = [v.get('name') for v in variables or [] if isinstance(v, dict)]
    raise ValueError("variable '" + name + "' is not declared in the task params. Declared: " + str(declared))


def input_path(working_path, var):
    return os.path.join(working_path, str(var.get('dataType') or 'variable'), str(var['id']))


def output_path(working_path, var):
    return os.path.join(working_path, ARTIFACTS_DIR, str(var['id']))


# ---------------------------------------------------------------------------------------------------
# THE CORE

def load_adapter(fund, importer=importlib.import_module):
    """The adapter module of a fund. importer is a parameter so the lookup and the import go through one function."""
    module = ADAPTERS.get((fund or '').strip())
    if module is None:
        raise ValueError("no adapter for fund '" + str(fund) + "'. Known funds: " + str(sorted(ADAPTERS)))
    return importer(module)


def split_credential(raw):
    """(login, password) from the Vault's plain login:password. The login is everything before the first colon;
    the password may contain colons. A trailing line break is dropped. The value is never put into a message."""
    text = bytes(raw).strip(b'\r\n').decode('utf-8')
    login, colon, password = text.partition(':')
    if not colon:
        raise ValueError('the Vault entry must hold the plain login:password of the fund account, but the value '
                         'handed over has no colon (the value is not printed)')
    if not login.strip():
        raise ValueError('the Vault entry holds an empty login (the value is not printed)')
    if not password:
        raise ValueError('the Vault entry holds an empty password (the value is not printed)')
    return login.strip(), password


def is_identifier(value):
    return isinstance(value, str) and bool(IDENTIFIER.match(value))


def _one_line(text, limit):
    text = re.sub(r'\s+', ' ', str(text)).strip()
    return text if len(text) <= limit else text[:limit] + '...'


def _first_text(d, keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return None


def _ident(d):
    for k in IDENT_KEYS:
        v = d.get(k)
        if is_identifier(v):
            return v
        if isinstance(v, int) and not isinstance(v, bool):
            return str(v)
    return None


def _required(d):
    for k in REQUIRED_KEYS:
        if isinstance(d.get(k), bool):
            return d[k]
    for k in OPTIONAL_KEYS:
        if isinstance(d.get(k), bool):
            return not d[k]
    return None


def _options(d):
    for k in OPTION_KEYS:
        v = d.get(k)
        if isinstance(v, list) and v:
            out = []
            for item in v:
                if isinstance(item, dict):
                    value = item.get('value', _ident(item))
                    out.append({'value': value, 'label': _first_text(item, LABEL_KEYS)})
                else:
                    out.append({'value': item, 'label': None})
            return out
    return None


def _limits(d):
    limits = {k: d[k] for k in LIMIT_KEYS if isinstance(d.get(k), (int, float)) and not isinstance(d.get(k), bool)}
    return limits or None


def _field(d, path):
    """A field definition read from d, or None when d does not define one: it needs a label and an identity."""
    label = _first_text(d, LABEL_KEYS)
    key = _ident(d)
    if label is None or key is None:
        return None
    type_value = _first_text(d, TYPE_KEYS)
    help_text = _first_text(d, HELP_KEYS)
    return {
        'key': key,
        'label': _one_line(label, LABEL_MAX),
        'type': type_value.strip() if type_value else None,
        'required': _required(d),
        'options': _options(d),
        'limits': _limits(d),
        'help': _one_line(help_text, LABEL_MAX) if help_text else None,
        'section': None,
        'path': path,
    }


def extract_fields(props):
    """Every field definition in an Inertia page's props, in document order.

    A dict is a field when it carries a label (label | question | prompt | title) and an identity (name | key |
    field | attribute | slug | id). Two exclusions keep containers and choices out:
      - a dict with a field anywhere beneath it is a CONTAINER (a section, a page), not a field; its label
        becomes the section of the fields beneath it
      - a dict inside an options / choices list is a CHOICE of its field, never a field of its own
    """
    def walk(value, path, in_options):
        if isinstance(value, dict):
            found = []
            for k, v in value.items():
                found.extend(walk(v, path + '.' + k, k in OPTION_KEYS))
            if found:
                section = _first_text(value, LABEL_KEYS)
                if section:
                    for f in found:
                        if f['section'] is None:
                            f['section'] = _one_line(section, LABEL_MAX)
                return found
            if in_options:
                return []
            field = _field(value, path)
            return [field] if field else []
        if isinstance(value, list):
            found = []
            for i, v in enumerate(value):
                found.extend(walk(v, path + '[' + str(i) + ']', in_options))
            return found
        return []

    return walk(props, 'props', False)


def variable_name(fund, key):
    """The apply flow's input Variable for a field: the fund, then the key's words in PascalCase.
    company_name -> ycCompanyName, companyUrl -> ycCompanyUrl, 1234 -> ycField1234."""
    words = [w for w in re.split(r'[^A-Za-z0-9]+', str(key)) if w]
    tail = ''.join(w[0].upper() + w[1:] for w in words)
    if not tail or tail[0].isdigit():
        tail = 'Field' + tail
    return (fund + tail)[:60]


def assign_variable_names(fund, fields):
    """Each field with its variable name; a name already taken gets 2, 3, ... appended."""
    taken = {}
    named = []
    for f in fields:
        base = variable_name(fund, f['key'])
        n = taken.get(base, 0) + 1
        taken[base] = n
        named.append({**f, 'variable': base if n == 1 else base + str(n)})
    return named


def variables_block(fields):
    """The variables { } block of the apply flow: one input per field, '?' unless the form says it is required."""
    lines = ['variables {']
    for f in fields:
        facts = [f['type'] or 'type unknown',
                 'required' if f['required'] is True else ('optional' if f['required'] is False else 'required unknown')]
        lines.append('    // ' + _one_line(f['label'], 100) + ' (' + ', '.join(facts) + ')')
        lines.append('    <- ' + f['variable'] + ('' if f['required'] is True else '?'))
    lines.append('}')
    return '\n'.join(lines) + '\n'


def skeleton(value, key=None, depth=0, in_options=False):
    """The shape of a props tree with no applicant content in it.

    Kept as is: every key; booleans; numbers under a limit or identity key; strings under a label, type or help
    key; identifier-shaped strings under an identity key; every string inside an options / choices list.
    Everything else is replaced: a string by 'str:<length>', a number by 'number'. A list shows its length and
    its first items."""
    if depth > SKELETON_MAX_DEPTH:
        return '...'
    if isinstance(value, dict):
        return {k: skeleton(v, k, depth + 1, in_options or k in OPTION_KEYS) for k, v in value.items()}
    if isinstance(value, list):
        return {'#': len(value), 'items': [skeleton(v, key, depth + 1, in_options) for v in value[:SKELETON_LIST_ITEMS]]}
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value if key in LIMIT_KEYS or key in IDENT_KEYS else 'number'
    if isinstance(value, str):
        if in_options or key in LABEL_KEYS or key in TYPE_KEYS or key in HELP_KEYS:
            return _one_line(value, SKELETON_TEXT_MAX)
        if key in IDENT_KEYS and is_identifier(value):
            return value
        return 'str:' + str(len(value))
    return type(value).__name__


def inventory(fund, page, fields):
    return {
        'fund': fund,
        'form': {'host': page.get('host'), 'path': page.get('path'), 'component': page.get('component'),
                 'version': page.get('version')},
        'fieldCount': len(fields),
        'fields': fields,
        'propsSkeleton': skeleton(page.get('props')),
    }


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
    from vc_http import open_session

    metas = task.get('metas') or []
    work_dir = task['workingPath']
    inputs = task.get('inputs')
    outputs = task.get('outputs')

    def read_input(role):
        var = find_variable(inputs, require_meta(metas, 'variable-for-' + role))
        if var.get('empty'):
            return None
        return read_text(input_path(work_dir, var))

    fund = require_meta(metas, 'fund')
    adapter = load_adapter(fund)
    form_url = (read_input('form-url') or '').strip()
    production = read_input('production')
    # resolved BEFORE the fund's site is called: a missing output declaration is a SourceCode defect
    fields_target = output_path(work_dir, find_variable(outputs, require_meta(metas, 'variable-for-form-fields')))
    variables_target = output_path(work_dir, find_variable(outputs, require_meta(metas, 'variable-for-apply-variables')))
    print('fund: ' + fund + ', production: ' + repr(production.strip() if production else None)
          + ' (a survey reads only; production changes nothing)')

    if credential is None:
        raise ValueError('no credential was handed over: the Function descriptor must declare the fund\'s Vault '
                         'entry as api.keyCode, but the params file carries no secretPort / checkCode')
    login, password = split_credential(credential)

    session = open_session(adapter.may_send, print)
    page = adapter.survey(session, login, password, form_url, print)
    print('form page: ' + str(page.get('component')) + ' at ' + str(page.get('host')) + str(page.get('path')))

    extract = getattr(adapter, 'extract_fields', extract_fields)
    fields = assign_variable_names(fund, extract(page.get('props')))
    write_text(fields_target, json.dumps(inventory(fund, page, fields), indent=2, ensure_ascii=False))
    write_text(variables_target, variables_block(fields))
    print('fields found: ' + str(len(fields)))
    for f in fields:
        print('  ' + f['variable'] + ' <- ' + f['key'] + ' (' + str(f['type']) + ', required=' + str(f['required'])
              + ')')
    return 0


def main(argv):
    # imported here: the core above must stay importable by a test on a box without PyYAML
    import yaml
    from mh_secret_client import exchange, extract_secret_fields, zero

    print(FUNCTION_TYPE)
    print('Cwd: ', os.getcwd())
    print('Script: ', os.path.abspath(__file__))

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
        print('FAILED: ' + type(e).__name__ + ': ' + str(e))
        return 1
    finally:
        if credential is not None:
            zero(credential)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
