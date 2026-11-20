# mh.asset.vc-update-<fund>_1.0 - sign in to a VC fund's application site and submit an update to an application
# that is already submitted: the answers the run brings that differ from what the fund holds, sent the way the fund's
# own page submits an update. A first submit is never made here.
#
# This file is NOT part of any bundle. It is reached only through the git block of a vc-application Function
# descriptor (vc-application/functions/fn-vc-update-<fund>/mh-function.yaml). It shares its payload directory with
# vc_apply.py and vc_form_survey.py: the fund adapters (vc_fund_<fund>.py), the HTTP session (vc_http.py), the page
# reader (vc_page.py), the secret client, and the generic core of vc_apply.py, which this file reuses.
#
# WHY A FLOW OF ITS OWN (vc-application/DETAILS.md, section C): after a submit, YC keeps only some questions editable,
# and a change is an update - a distinct act YC records and shows as "Update submitted" - not an autosave of a draft.
# The apply refuses a submitted application (vc_apply.write_refusal); this Function refuses one that is not submitted.
#
# MODES (DAHF §0.15): production exactly when the production input is exactly "true".
#   synthetic   sign in, read the update form and the application, compute the update - and send nothing
#   production  the same, then one submitted update, then the application read again and compared
# Either way the adapter's session guard (may_send_apply) and the GraphQL operation guard (graphql_body: the write
# operation is allowed only in production) are asked before anything leaves the Processor.
#
# THE ANSWERS are the run's input Variables named <prefix><Question>, as for the apply. A NULL input leaves that
# question as the fund holds it. An answer to a question the update form does not have refuses the whole run - after
# the read, so the run's outputs show what the form offers, and before anything is written.
#
# REUSABLE BY CONSTRUCTION - every name is a meta:
#   fund                           meta    the adapter, e.g. yc
#   variable-prefix                meta    the prefix of the answer inputs, e.g. yc
#   variable-for-form-url          INPUT   the application's url
#   variable-for-production        INPUT   nullable; exactly "true" is production
#   variable-for-current-answers   OUTPUT  JSON: the update form (kind, questions), the application's status and answers
#   variable-for-update-patch      OUTPUT  JSON: which answers differ, refusals, and the update a production run sends
#   variable-for-update-result     OUTPUT  JSON: what was sent, the fund's answer, the read-back comparison
#
# THE CREDENTIAL comes from the Vault over the loopback secret channel, exactly as for the apply.

import os
import sys

from vc_apply import (answers_from_inputs, check_answers, compute_patch, find_variable, is_production, load_adapter,
                      others_changed, output_path, patch_report, read_back_mismatches, read_text, require_meta,
                      input_path, write_json)

FUNCTION_TYPE = 'mh.asset.vc-update'


# ---------------------------------------------------------------------------------------------------
# THE CORE

def update_plan(adapter, ctx, app, answers):
    """Everything an update decides before it writes: the refused answers, the patch against what the fund holds, the
    input a production run would send, and why it must not be sent (None when it may)."""
    current = app.get('questions') or {}
    readable = set(adapter.readable_keys(ctx['formKeys']))
    not_writable = tuple(adapter.NOT_WRITABLE) + tuple(k for k in ctx['formKeys'] if k not in readable)
    problems = check_answers(answers, ctx['formKeys'], not_writable, adapter.CHOICES, adapter.LIMITS)
    patch = {} if problems else compute_patch(answers, current)
    refusal = adapter.update_refusal(app, ctx['updateKind'])
    update_input = None
    if not problems and patch and refusal is None:
        update_input = adapter.update_submit_input(adapter.update_questions(ctx['formKeys'], current, patch),
                                                   ctx['updateKind'])
    return {'problems': problems, 'patch': patch, 'refusal': refusal, 'updateInput': update_input}


# ---------------------------------------------------------------------------------------------------
# THE BOUNDARY

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
    patch_target = output_path(work_dir, find_variable(outputs, require_meta(metas, 'variable-for-update-patch')))
    result_target = output_path(work_dir, find_variable(outputs, require_meta(metas, 'variable-for-update-result')))

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
    # E1 (ExecContext #11491): a submitted application's /edit is the page that chooses an update kind, not a form
    kinds = adapter.update_kinds(page['html'])
    if kinds is not None:
        raise ValueError('formUrl names the page that chooses an update kind, not an update form - give the kind\'s '
                         'page, ' + form_url.rstrip('/') + '/<kind>, one of: '
                         + ', '.join(k + ' (' + str(v) + ')' for k, v in kinds.items()))
    ctx = adapter.form_context(page['html'])
    print('form: ' + str(page['host']) + str(page['path']) + ', questions: ' + str(len(ctx['formKeys']))
          + ', updateKind: ' + str(ctx['updateKind']))

    app = adapter.read_all_answers(session, ctx, form_url, allowed_ops, print)
    current = app.get('questions') or {}
    status = {k: v for k, v in app.items() if k != 'questions'}
    write_json(current_target, {'fund': fund, 'form': {'updateKind': ctx['updateKind'], 'formKeys': ctx['formKeys']},
                                'status': status, 'questions': current})
    plan = update_plan(adapter, ctx, app, answers)
    patch = plan['patch']
    write_json(patch_target, {'mode': mode, 'updateKind': ctx['updateKind'], 'refused': plan['problems'],
                              **patch_report(answers, current, patch), 'refusal': plan['refusal'],
                              'updateInput': plan['updateInput']})
    print('read: submitted=' + str(app.get('submitted')) + ', editable=' + str(app.get('editable')) + ', fullEditable='
          + str(app.get('fullEditable')) + ', status=' + str(app.get('status')) + '; differing: ' + str(len(patch))
          + ' (' + ', '.join(patch) + '); refusal: ' + str(plan['refusal']))

    if plan['problems']:
        for p in plan['problems']:
            print('REFUSED ANSWER: ' + p)
        write_json(result_target, {'mode': mode, 'sent': False, 'refused': plan['problems']})
        raise ValueError(str(len(plan['problems'])) + ' answer(s) refused - nothing was written')

    if not production:
        write_json(result_target, {'mode': mode, 'sent': False, 'wouldSend': list(patch), 'refusal': plan['refusal']})
        print('synthetic: nothing sent')
        return 0

    if plan['refusal']:
        write_json(result_target, {'mode': mode, 'sent': False, 'refusal': plan['refusal']})
        raise RuntimeError('not written: ' + plan['refusal'])
    if not patch:
        write_json(result_target, {'mode': mode, 'sent': False, 'reason': 'every answer is already held'})
        print('production: every answer is already held - nothing sent')
        return 0

    answer = adapter.submit_update(session, ctx, plan['updateInput']['questions'], form_url, allowed_ops, print)
    after_app = adapter.read_all_answers(session, ctx, form_url, allowed_ops, print)
    after = after_app.get('questions') or {}
    mismatches = read_back_mismatches(patch, after)
    changed_outside = others_changed(patch, current, after)
    ok = answer.get('success') is True and not answer.get('errors') and not mismatches and not changed_outside
    write_json(result_target, {
        'mode': mode, 'sent': True, 'updateKind': ctx['updateKind'], 'savedQuestions': list(patch),
        'success': answer.get('success'), 'persisted': answer.get('persisted'), 'errors': answer.get('errors'),
        'readBackMismatches': mismatches, 'othersChanged': changed_outside,
        'submittedAfter': after_app.get('submitted'), 'statusAfter': after_app.get('status'),
        'heldAfter': {k: after.get(k) for k in mismatches},
    })
    print('production: update sent with ' + str(len(patch)) + ' changed, success=' + str(answer.get('success'))
          + ', persisted=' + str(answer.get('persisted')) + ', errors=' + str(answer.get('errors'))
          + ', read back differs: ' + str(mismatches) + ', changed outside the patch: ' + str(changed_outside))
    if not ok:
        print('FAILED: the update was not confirmed by YC or by the read-back')
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
