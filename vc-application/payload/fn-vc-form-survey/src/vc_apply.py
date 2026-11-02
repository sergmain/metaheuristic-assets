# mh.asset.vc-apply-<fund>_1.0 - sign in to a VC fund's application site, read the application's current answers,
# and save every answer the run brings that differs from what the fund holds. The application is filled, never
# submitted.
#
# This file is NOT part of any bundle. It is reached only through the git block of a vc-application Function
# descriptor (vc-application/functions/fn-vc-apply-<fund>/mh-function.yaml). It shares its payload directory with
# vc_form_survey.py: the fund adapters (vc_fund_<fund>.py), the HTTP session (vc_http.py), the page reader
# (vc_page.py) and the secret client are the same modules.
#
# MODES (DAHF §0.15): production exactly when the production input is exactly "true".
#   synthetic   sign in, read the current answers, compute what would be sent - and send nothing
#   production  the same, then one save of the differing answers, then the answers read again and compared
# Either way the adapter's session guard (may_send_apply) and the GraphQL operation guard (graphql_body: the write
# operation is allowed only in production) are asked before anything leaves the Processor.
#
# THE ANSWERS are the run's input Variables named <prefix><Question> - meta 'variable-prefix', e.g. yc: ycName is the
# question 'name', ycFutureBatchName 'futureBatchName'. A NULL input leaves that question as the fund holds it; any
# other value, the empty string included, is what the question is to hold. Every answer is checked before the
# fund's site is written: a question the form does not have, an upload, a choice outside its values or an answer
# over the form's limit refuses the whole run - nothing is written in part.
#
# REUSABLE BY CONSTRUCTION - every name is a meta:
#   fund                           meta    the adapter, e.g. yc
#   variable-prefix                meta    the prefix of the answer inputs, e.g. yc
#   variable-for-form-url          INPUT   the application's url
#   variable-for-production        INPUT   nullable; exactly "true" is production
#   variable-for-current-answers   OUTPUT  JSON: the application's status and answers as read before any write
#   variable-for-apply-patch       OUTPUT  JSON: which answers differ, and the patch a production run sends
#   variable-for-apply-result      OUTPUT  JSON: what was sent, the fund's answer, the read-back comparison
#
# THE CREDENTIAL comes from the Vault over the loopback secret channel, exactly as for the survey; it is never
# printed and its buffer is zeroed on the way out.
#
# The core below is what vc-application/tests exercises: pure functions. run() and main() are the boundary.

import importlib
import json
import os
import sys

FUNCTION_TYPE = 'mh.asset.vc-apply'

# fund -> adapter module, a sibling of this file (the same adapters vc_form_survey.py loads)
ADAPTERS = {
    'yc': 'vc_fund_yc',
}

ARTIFACTS_DIR = 'artifacts'


# ---------------------------------------------------------------------------------------------------
# THE CORE

def load_adapter(fund, importer=importlib.import_module):
    module = ADAPTERS.get((fund or '').strip())
    if module is None:
        raise ValueError("no adapter for fund '" + str(fund) + "'. Known funds: " + str(sorted(ADAPTERS)))
    return importer(module)


def is_production(text):
    """Production exactly when the input's content is "true"; a null, false or anything else is synthetic."""
    return text is not None and text.strip() == 'true'


def question_key(prefix, variable):
    """The question an answer input is for: the variable without the prefix, its first letter lowered."""
    if not variable.startswith(prefix) or len(variable) == len(prefix):
        raise ValueError("input '" + variable + "' does not name a question after the prefix '" + prefix + "'")
    tail = variable[len(prefix):]
    return tail[0].lower() + tail[1:]


def answers_from_inputs(prefix, values):
    """{question: answer} for every answer input that is not null, in the inputs' order."""
    answers = {}
    for name, value in values.items():
        key = question_key(prefix, name)
        if key in answers:
            raise ValueError("two inputs name the question '" + key + "'")
        if value is not None:
            answers[key] = value
    return answers


def check_answers(answers, form_keys, not_writable, choices, limits):
    """Every problem that refuses the run, one line each; [] when every answer may be written."""
    problems = []
    for key, value in answers.items():
        if key not in form_keys:
            problems.append(key + ': not a question of the form (the form changed, or the input is misnamed)')
        elif key in not_writable:
            problems.append(key + ': an upload, a profile or a non-text question - an apply does not write it')
        elif not isinstance(value, str):
            problems.append(key + ': the answer is not text')
        elif key in choices and value not in choices[key]:
            problems.append(key + ": '" + value + "' is not one of " + ', '.join(choices[key]))
        elif key in limits and len(value) > limits[key]:
            problems.append(key + ': ' + str(len(value)) + ' characters, the form allows ' + str(limits[key]))
    return problems


def held(value):
    """A question's value as the fund holds it, for comparison: an unanswered question holds the empty string."""
    return '' if value is None else value


def compute_patch(answers, current):
    """The answers that differ from what the fund holds, in the answers' order."""
    return {k: v for k, v in answers.items() if held(current.get(k)) != v}


def read_back_mismatches(patch, after):
    """The questions of a sent patch that do not hold the sent value when read again."""
    return [k for k, v in patch.items() if held(after.get(k)) != v]


def others_changed(patch, before, after):
    """The questions outside a sent patch whose value is not what it was before the save."""
    return [k for k in sorted(set(before) | set(after)) if k not in patch and before.get(k) != after.get(k)]


def patch_report(answers, current, patch):
    return {
        'answersGiven': len(answers),
        'differing': list(patch),
        'alreadyHeld': [k for k in answers if k not in patch],
        'patch': patch,
        'heldBefore': {k: current.get(k) for k in patch},
    }


def write_refusal(app):
    """Why a production run must not write to this application, or None."""
    if app.get('submitted'):
        return 'the application is already submitted'
    if app.get('editable') is False:
        return 'YC marks the application as not editable'
    return None


# ---------------------------------------------------------------------------------------------------
# THE BOUNDARY

def meta_value(metas, key):
    for meta in metas or []:
        if isinstance(meta, dict) and meta.get(key) is not None:
            return str(meta.get(key))
    return None


def require_meta(metas, key):
    value = meta_value(metas, key)
    if value is None or not value.strip():
        keys = sorted({k for m in metas or [] if isinstance(m, dict) for k in m})
        raise ValueError("meta '" + key + "' is required and was not declared. Declared metas: " + str(keys))
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


def read_text(path):
    with open(path, 'r', encoding='utf-8', newline='') as f:
        return f.read()


def write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(value, indent=2, ensure_ascii=False))


def run(task, credential):
    from vc_form_survey import split_credential
    from vc_http import open_session

    metas = task.get('metas') or []
    work_dir = task['workingPath']
    inputs = task.get('inputs') or []
    outputs = task.get('outputs')

    def read_var(var):
        return None if var.get('empty') else read_text(input_path(work_dir, var))

    fund = require_meta(metas, 'fund')
    prefix = require_meta(metas, 'variable-prefix')
    adapter = load_adapter(fund)
    form_url_name = require_meta(metas, 'variable-for-form-url')
    production_name = require_meta(metas, 'variable-for-production')
    form_url = (read_var(find_variable(inputs, form_url_name)) or '').strip()
    production = is_production(read_var(find_variable(inputs, production_name)))
    # resolved BEFORE the fund's site is called: a missing output declaration is a SourceCode defect
    current_target = output_path(work_dir, find_variable(outputs, require_meta(metas, 'variable-for-current-answers')))
    patch_target = output_path(work_dir, find_variable(outputs, require_meta(metas, 'variable-for-apply-patch')))
    result_target = output_path(work_dir, find_variable(outputs, require_meta(metas, 'variable-for-apply-result')))

    values = {v['name']: read_var(v) for v in inputs
              if isinstance(v, dict) and str(v.get('name') or '').startswith(prefix)
              and v.get('name') not in (form_url_name, production_name)}
    answers = answers_from_inputs(prefix, values)
    mode = 'production' if production else 'synthetic'
    print('fund: ' + fund + ', mode: ' + mode + ', answer inputs: ' + str(len(values)) + ', answers given: '
          + str(len(answers)) + ' (' + ', '.join(answers) + ')')

    if credential is None:
        raise ValueError('no credential was handed over: the Function descriptor must declare the fund\'s Vault '
                         'entry as api.keyCode, but the params file carries no secretPort / checkCode')
    login, password = split_credential(credential)
    allowed_ops = adapter.READ_OPS + (adapter.WRITE_OPS if production else ())

    session = open_session(adapter.may_send_apply, print)
    page = adapter.survey(session, login, password, form_url, print)
    ctx = adapter.form_context(page['html'])
    print('form: ' + str(page['host']) + str(page['path']) + ', questions: ' + str(len(ctx['formKeys']))
          + ', updateKind: ' + str(ctx['updateKind']))

    # a question the adapter cannot read (not a field of the fund's answers) is not written either (E1, #7433)
    readable = set(adapter.readable_keys(ctx['formKeys']))
    not_writable = tuple(adapter.NOT_WRITABLE) + tuple(k for k in ctx['formKeys'] if k not in readable)
    problems = check_answers(answers, ctx['formKeys'], not_writable, adapter.CHOICES, adapter.LIMITS)
    if problems:
        for p in problems:
            print('REFUSED ANSWER: ' + p)
        raise ValueError(str(len(problems)) + ' answer(s) refused - nothing was written')

    app = adapter.read_answers(session, ctx, form_url, allowed_ops, print)
    current = app.get('questions') or {}
    status = {k: v for k, v in app.items() if k != 'questions'}
    write_json(current_target, {'fund': fund, 'status': status, 'questions': current})
    patch = compute_patch(answers, current)
    write_json(patch_target, {'mode': mode, **patch_report(answers, current, patch)})
    print('read: submitted=' + str(app.get('submitted')) + ', editable=' + str(app.get('editable'))
          + ', answered: ' + str(sum(1 for v in current.values() if v not in (None, '', [])))
          + ' of ' + str(len(current)) + '; differing: ' + str(len(patch)) + ' (' + ', '.join(patch) + ')')

    if not production:
        write_json(result_target, {'mode': mode, 'sent': False, 'wouldSend': list(patch)})
        print('synthetic: nothing sent')
        return 0

    refusal = write_refusal(app)
    if refusal:
        write_json(result_target, {'mode': mode, 'sent': False, 'refused': refusal})
        raise RuntimeError('not written: ' + refusal)
    if not patch:
        write_json(result_target, {'mode': mode, 'sent': False, 'reason': 'every answer is already held'})
        print('production: every answer is already held - nothing sent')
        return 0

    answer = adapter.write_answers(session, ctx, patch, form_url, allowed_ops, print)
    after_app = adapter.read_answers(session, ctx, form_url, allowed_ops, print)
    after = after_app.get('questions') or {}
    mismatches = read_back_mismatches(patch, after)
    changed_outside = others_changed(patch, current, after)
    ok = answer.get('success') is True and not answer.get('errors') and not mismatches and not changed_outside
    write_json(result_target, {
        'mode': mode, 'sent': True, 'savedQuestions': list(patch),
        'success': answer.get('success'), 'persisted': answer.get('persisted'), 'errors': answer.get('errors'),
        'readBackMismatches': mismatches, 'othersChanged': changed_outside,
        'submittedAfter': after_app.get('submitted'),
        'heldAfter': {k: after.get(k) for k in mismatches},
    })
    print('production: sent ' + str(len(patch)) + ', success=' + str(answer.get('success')) + ', persisted='
          + str(answer.get('persisted')) + ', errors=' + str(answer.get('errors')) + ', read back differs: '
          + str(mismatches) + ', changed outside the patch: ' + str(changed_outside))
    if not ok:
        print('FAILED: the save was not confirmed by YC or by the read-back')
        return 1
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
