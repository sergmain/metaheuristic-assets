# Unit tests of the update: the core of vc_update.py and the update part of the YC adapter (vc_fund_yc.py).
# Synthetic: every test builds its own input; nothing reads a fund's site or production data.
import html
import json

import pytest

import vc_fund_yc as yc
import vc_update as u

# a progress update form, as the page's update_kind 'progress' shows one (the questions are the test's own choice)
PROGRESS_KEYS = ['howfar', 'worked', 'techstack', 'stage', 'whenbeta', 'revenue', 'revenueamount', 'since']
SUBMITTED = {'submitted': True, 'editable': True, 'fullEditable': False, 'status': 'submitted'}


def _ctx(keys=None, update_kind='progress'):
    return {'csrf': 't', 'appUuid': 'u-1', 'updateKind': update_kind, 'formKeys': list(keys or PROGRESS_KEYS),
            'futureBatchNames': None}


def _app(questions, **status):
    return {**SUBMITTED, **status, 'questions': questions}


# ---------------------------------------------------------------------------------------------------
# the adapter

def test_update_questions_carry_every_question_of_the_form_with_the_patch_applied():
    held = {'howfar': 'old', 'worked': 'w', 'techstack': 't', 'stage': '1', 'whenbeta': None, 'revenue': 'no',
            'revenueamount': None, 'since': 's', 'get': 'not in the form'}
    q = yc.update_questions(PROGRESS_KEYS, held, {'howfar': 'new'})
    assert list(q) == PROGRESS_KEYS
    assert q['howfar'] == 'new' and q['worked'] == 'w' and q['whenbeta'] is None
    assert 'get' not in q


def test_update_questions_send_revenueamount_json_stringified_as_the_page_does():
    q = yc.update_questions(['revenueamount'], {'revenueamount': [{'val': 10, 'month': '2026-10'}]}, {})
    assert q['revenueamount'] == '[{"val":10,"month":"2026-10"}]'
    assert yc.update_questions(['revenueamount'], {}, {})['revenueamount'] == 'null'


def test_update_questions_never_carry_uploads_or_profiles():
    q = yc.update_questions(['videoS3Key', 'demoS3Key', 'founderBios', 'video', 'howfar'], {'howfar': 'h'}, {})
    assert list(q) == ['howfar']


def test_update_submit_input_is_a_submitted_update_and_never_touches_the_applicants():
    i = yc.update_submit_input({'howfar': 'h'}, 'progress')
    assert i == {'questions': {'howfar': 'h'}, 'submitOnSave': 1, 'updateKind': 'progress'}
    assert 'applicantsAttributes' not in i and 'autosave' not in i


def test_update_submit_input_without_an_update_kind_is_refused_it_would_be_a_first_submit():
    for kind in (None, '', '  '):
        with pytest.raises(yc.OperationRefused):
            yc.update_submit_input({'howfar': 'h'}, kind)
    with pytest.raises(ValueError):
        yc.update_submit_input({}, 'progress')


def test_update_refusal():
    assert yc.update_refusal(SUBMITTED, 'progress') is None
    assert yc.update_refusal({**SUBMITTED, 'editable': False, 'fullEditable': True}, 'full') is None
    assert 'not submitted' in yc.update_refusal({**SUBMITTED, 'submitted': False}, 'progress')
    assert 'neither editable' in yc.update_refusal({**SUBMITTED, 'editable': False}, 'progress')
    assert 'no update_kind' in yc.update_refusal(SUBMITTED, None)


def test_the_update_write_is_sent_only_when_the_run_allows_it():
    query = yc.update_app_mutation(['howfar'])
    variables = {'uuid': 'u', 'input': yc.update_submit_input({'howfar': 'h'}, 'progress')}
    with pytest.raises(yc.OperationRefused):
        yc.graphql_body('UPDATE_APP', query, variables, yc.READ_OPS)
    body = yc.graphql_body('UPDATE_APP', query, variables, yc.READ_OPS + yc.WRITE_OPS)
    assert body['variables']['input']['submitOnSave'] == 1


def _inertia_page(component, props):
    # the shape of YC's apply pages since November 2026 (survey E2 of the update, ExecContext #11492): Inertia's
    # data-page attribute
    page = {'component': component, 'props': props, 'url': '/apps/u/edit', 'version': 'v'}
    return ('<html><head><meta name="csrf-token" content="tok"></head><body><div id="app" data-page="'
            + html.escape(json.dumps(page), quote=True) + '"></div></body></html>')


def test_update_kinds_reads_the_page_that_chooses_an_update_kind():
    page = _inertia_page('apply/ChooseUpdateKind', {
        'visible_update_kinds': {'progress': {'label': 'Progress Update', 'summary': 's'},
                                 'fundraise': {'label': 'Fundraising Update', 'summary': 's'}},
        'app_uuid': 'u'})
    assert yc.update_kinds(page) == {'progress': 'Progress Update', 'fundraise': 'Fundraising Update'}


def test_update_kinds_is_none_on_a_kind_form_which_form_context_reads():
    page = _inertia_page('apply/AppForm', {
        'app_uuid': 'u-9', 'update_kind': 'progress', 'future_batch_names': [],
        'active_question_groups': {'Progress': {'howfar': {'prompt': {'q': 'How far along are you?'}},
                                                'techstack': {'prompt': {'q': 'Tech stack?'}}}}})
    assert yc.update_kinds(page) is None
    ctx = yc.form_context(page)
    assert ctx['updateKind'] == 'progress' and ctx['formKeys'] == ['howfar', 'techstack'] and ctx['appUuid'] == 'u-9'


def test_the_wide_read_selects_every_question_and_no_upload():
    keys = yc.readable_keys(yc.APP_QUESTIONS)
    assert 'get' in keys and 'howfar' in keys and 'sched' in keys
    assert not set(keys) & {'videoS3Key', 'demoS3Key', 'founderBios'}
    q = yc.show_app_query(keys)
    assert q.count('{') == q.count('}')


# ---------------------------------------------------------------------------------------------------
# the core

def test_update_plan_patches_the_differing_answers_and_builds_the_input():
    app = _app({'howfar': 'old', 'techstack': 'same', 'revenueamount': None})
    plan = u.update_plan(yc, _ctx(), app, {'howfar': 'new', 'techstack': 'same'})
    assert plan['problems'] == [] and plan['refusal'] is None
    assert plan['patch'] == {'howfar': 'new'}
    assert plan['updateInput']['updateKind'] == 'progress' and plan['updateInput']['submitOnSave'] == 1
    assert plan['updateInput']['questions']['howfar'] == 'new'
    assert plan['updateInput']['questions']['techstack'] == 'same'
    assert set(plan['updateInput']['questions']) == set(PROGRESS_KEYS)


def test_update_plan_refuses_an_answer_to_a_question_the_update_form_does_not_offer():
    plan = u.update_plan(yc, _ctx(), _app({'get': 'old'}), {'get': 'new', 'howfar': 'h'})
    assert len(plan['problems']) == 1 and plan['problems'][0].startswith('get: not a question of the form')
    assert plan['patch'] == {} and plan['updateInput'] is None


def test_update_plan_builds_no_input_for_an_application_not_submitted():
    plan = u.update_plan(yc, _ctx(), _app({'howfar': 'old'}, submitted=False), {'howfar': 'new'})
    assert plan['patch'] == {'howfar': 'new'}
    assert 'not submitted' in plan['refusal'] and plan['updateInput'] is None


def test_update_plan_with_nothing_differing_builds_no_input():
    plan = u.update_plan(yc, _ctx(), _app({'howfar': 'same'}), {'howfar': 'same'})
    assert plan['patch'] == {} and plan['updateInput'] is None and plan['refusal'] is None


def test_update_plan_without_answers_is_a_read_only():
    plan = u.update_plan(yc, _ctx(update_kind=None), _app({'howfar': 'h'}), {})
    assert plan['patch'] == {} and plan['updateInput'] is None
    assert 'no update_kind' in plan['refusal']
    json.dumps(plan)
