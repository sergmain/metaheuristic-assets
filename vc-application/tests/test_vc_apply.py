# Unit tests of the apply: the generic core of vc_apply.py and the apply part of the YC adapter (vc_fund_yc.py).
# Synthetic: every test builds its own input; nothing reads a fund's site or production data.
import json

import pytest

import vc_apply as a
import vc_fund_yc as yc

# the 51 answer inputs E5 defined (DETAILS.md part 3, ExecContext #5406), as the apply .mhsc declares them
YC_INPUTS = [
    'ycFounderBios', 'ycMeet', 'ycOthers2', 'ycCofounder', 'ycVideo', 'ycVideoS3Key', 'ycName', 'ycDescribe', 'ycUrl',
    'ycDemo', 'ycDemoS3Key', 'ycProductLink', 'ycProductCreds', 'ycMake', 'ycWhere', 'ycWherewhy', 'ycHowfar',
    'ycWorked', 'ycTechstack', 'ycCodingAgentSession', 'ycStage', 'ycUsernums', 'ycWhenbeta', 'ycRevenue',
    'ycRevenueamount', 'ycRevenuesource', 'ycGrowthrate', 'ycSince', 'ycAcc', 'ycExp', 'ycGet', 'ycMoney', 'ycIdeas',
    'ycIncyet', 'ycInctype', 'ycIncpercent', 'ycPercent2', 'ycInvestyet', 'ycIncinvest', 'ycInvestamount', 'ycBank',
    'ycBurn', 'ycRunway', 'ycCurrentlyraising', 'ycRaisingdetails', 'ycWhyapply', 'ycHowhear', 'ycReferralCode',
    'ycBatchPreference', 'ycFutureBatchName', 'ycFutureBatchWhy',
]
YC_KEYS = [
    'founderBios', 'meet', 'others2', 'cofounder', 'video', 'videoS3Key', 'name', 'describe', 'url', 'demo',
    'demoS3Key', 'productLink', 'productCreds', 'make', 'where', 'wherewhy', 'howfar', 'worked', 'techstack',
    'codingAgentSession', 'stage', 'usernums', 'whenbeta', 'revenue', 'revenueamount', 'revenuesource', 'growthrate',
    'since', 'acc', 'exp', 'get', 'money', 'ideas', 'incyet', 'inctype', 'incpercent', 'percent2', 'investyet',
    'incinvest', 'investamount', 'bank', 'burn', 'runway', 'currentlyraising', 'raisingdetails', 'whyapply', 'howhear',
    'referralCode', 'batchPreference', 'futureBatchName', 'futureBatchWhy',
]

# ---------------------------------------------------------------------------------------------------
# the core


def test_every_yc_input_names_its_question():
    assert [a.question_key('yc', v) for v in YC_INPUTS] == YC_KEYS


def test_question_key_refuses_a_name_without_the_prefix_or_with_nothing_after_it():
    with pytest.raises(ValueError):
        a.question_key('yc', 'formUrl')
    with pytest.raises(ValueError):
        a.question_key('yc', 'yc')


def test_a_null_input_leaves_its_question_and_the_empty_string_is_an_answer():
    assert a.answers_from_inputs('yc', {'ycName': 'X', 'ycUrl': None, 'ycDemo': ''}) == {'name': 'X', 'demo': ''}


def test_is_production_only_for_exactly_true():
    assert a.is_production('true') and a.is_production('true\n')
    for text in (None, '', 'false', 'TRUE', 'True', 'yes', '1', 'null'):
        assert not a.is_production(text)


def test_check_answers_accepts_what_may_be_written():
    answers = {'name': 'Innovation Platforms', 'describe': 'x' * 50, 'stage': '1', 'batchPreference': 'current'}
    assert a.check_answers(answers, YC_KEYS, yc.NOT_WRITABLE, yc.CHOICES, yc.LIMITS) == []


def test_check_answers_names_every_problem():
    answers = {'nosuch': 'a', 'videoS3Key': 'k', 'founderBios': 'b', 'revenueamount': '[]', 'stage': 'yes',
               'incyet': 'Yes', 'describe': 'x' * 51}
    problems = a.check_answers(answers, YC_KEYS, yc.NOT_WRITABLE, yc.CHOICES, yc.LIMITS)
    assert [p.split(':')[0] for p in problems] == ['nosuch', 'videoS3Key', 'founderBios', 'revenueamount', 'stage',
                                                    'incyet', 'describe']
    assert '51 characters, the form allows 50' in problems[-1]


def test_compute_patch_keeps_only_what_differs_and_an_unanswered_question_holds_the_empty_string():
    current = {'name': 'Same', 'describe': 'old', 'url': None, 'demo': None}
    answers = {'name': 'Same', 'describe': 'new', 'url': 'https://x', 'demo': ''}
    assert a.compute_patch(answers, current) == {'describe': 'new', 'url': 'https://x'}


def test_read_back_mismatches_name_the_questions_that_do_not_hold_what_was_sent():
    patch = {'describe': 'new', 'url': 'https://x'}
    assert a.read_back_mismatches(patch, {'describe': 'new', 'url': 'https://x'}) == []
    assert a.read_back_mismatches(patch, {'describe': 'new', 'url': None}) == ['url']


def test_others_changed_names_what_moved_outside_the_patch():
    before = {'name': 'A', 'make': 'old', 'url': None}
    assert a.others_changed({'make': 'B'}, before, {'name': 'A', 'make': 'B', 'url': None}) == []
    assert a.others_changed({'make': 'B'}, before, {'name': 'Z', 'make': 'B', 'url': None}) == ['name']


def test_patch_report_separates_differing_from_already_held():
    report = a.patch_report({'name': 'A', 'make': 'B'}, {'name': 'A', 'make': 'old'}, {'make': 'B'})
    assert report['differing'] == ['make'] and report['alreadyHeld'] == ['name']
    assert report['heldBefore'] == {'make': 'old'}


def test_a_submitted_or_not_editable_application_is_never_written():
    assert a.write_refusal({'submitted': True, 'editable': True}) == 'the application is already submitted'
    assert a.write_refusal({'submitted': False, 'editable': False}) == 'YC marks the application as not editable'
    assert a.write_refusal({'submitted': False, 'editable': True}) is None


# ---------------------------------------------------------------------------------------------------
# the YC adapter's apply part


def test_may_send_apply_adds_exactly_the_graphql_post():
    assert yc.may_send_apply('POST', 'https://apply.ycombinator.com/graphql')
    assert yc.may_send_apply('GET', 'https://apply.ycombinator.com/apps/1/edit')
    assert yc.may_send_apply('POST', 'https://account.ycombinator.com/sign_in')
    assert not yc.may_send_apply('POST', 'https://apply.ycombinator.com/apps/1/edit')
    assert not yc.may_send_apply('POST', 'http://apply.ycombinator.com/graphql')
    assert not yc.may_send_apply('POST', 'https://account.ycombinator.com/graphql')
    assert not yc.may_send_apply('PUT', 'https://apply.ycombinator.com/graphql')
    assert not yc.may_send_apply('POST', 'https://apply.ycombinator.com.evil.example/graphql')


def test_a_survey_still_never_writes_to_the_application():
    assert not yc.may_send('POST', 'https://apply.ycombinator.com/graphql')


def test_graphql_body_allows_the_write_only_when_the_run_allows_it():
    q = yc.update_app_mutation(['name'])
    with pytest.raises(yc.OperationRefused):
        yc.graphql_body('UPDATE_APP', q, {}, yc.READ_OPS)
    body = yc.graphql_body('UPDATE_APP', q, {'uuid': 'u'}, yc.READ_OPS + yc.WRITE_OPS)
    assert body == {'operationName': 'UPDATE_APP', 'variables': {'uuid': 'u'}, 'query': q}


def test_graphql_body_refuses_an_unlisted_operation_and_a_text_that_is_not_its_operation():
    with pytest.raises(yc.OperationRefused):
        yc.graphql_body('SUBMIT_APP', 'mutation SUBMIT_APP($u: Uuid) { x }', {}, ('SUBMIT_APP',))
    with pytest.raises(yc.OperationRefused):
        yc.graphql_body('SHOW_APP', yc.update_app_mutation(['name']), {}, yc.READ_OPS + yc.WRITE_OPS)


def test_update_input_is_an_autosave_of_the_patch_and_never_a_submit():
    payload = yc.update_input({'make': 'B'}, None)
    assert payload == {'questions': {'make': 'B'}, 'autosave': 1}
    assert 'submitOnSave' not in payload and 'applicantsAttributes' not in payload
    assert yc.update_input({'make': 'B'}, 'founder')['updateKind'] == 'founder'
    with pytest.raises(ValueError):
        yc.update_input({}, None)


def test_the_read_selects_every_question_but_the_uploads_and_profiles():
    keys = yc.readable_keys(YC_KEYS)
    assert 'videoS3Key' not in keys and 'demoS3Key' not in keys and 'founderBios' not in keys
    assert len(keys) == len(YC_KEYS) - 3
    q = yc.show_app_query(keys)
    assert q.startswith('query SHOW_APP($appUuid: Uuid) {')
    for k in keys:
        assert '      ' + k in q
    assert 'revenueamount {\n        val\n        month\n      }' in q
    for f in ('submitted', 'editable', 'videoS3Key'):
        assert '    ' + f + '\n' in q
    assert q.count('{') == q.count('}')


def test_the_mutation_text_is_balanced_and_answers_with_the_questions():
    m = yc.update_app_mutation(yc.readable_keys(YC_KEYS))
    assert m.startswith('mutation UPDATE_APP($uuid: Uuid!, $input: UpdateAppInput!, $reloadApp: Boolean) {')
    assert m.count('{') == m.count('}')
    assert '        make\n' in m


def _app_form_page(props, token='tok-1'):
    # the shape YC's apply page has (E4, ExecContext #5319): bare wrapper keys, the props a JSON literal
    return ('<html><head><meta name="csrf-token" content="' + token + '"></head><body><div id="a1"></div><script>\n'
            'window.REACT_COMPONENTS = window.REACT_COMPONENTS || []\n'
            'window.REACT_COMPONENTS.push({ divId: "h1", component: "components/Header", props: {"x": 1} })\n'
            'window.REACT_COMPONENTS.push({ divId: "a1", component: "components/AppForm", props: '
            + json.dumps(props) + ' })\n</script></body></html>')


def test_form_context_reads_the_app_form():
    props = {'app_uuid': 'u-123', 'update_kind': None, 'user_hnid': 'h',
             'future_batch_names': ['Summer 2027'],
             'active_question_groups': {'founders': {'founderBios': {'prompt': None}, 'others2': {'prompt': {'q': 'Q'}}},
                                        'company': {'name': {'prompt': {'q': 'Company name', 'required': True}}}}}
    ctx = yc.form_context(_app_form_page(props))
    assert ctx == {'csrf': 'tok-1', 'appUuid': 'u-123', 'updateKind': None,
                   'formKeys': ['founderBios', 'others2', 'name'], 'futureBatchNames': ['Summer 2027']}


def test_form_context_keeps_an_update_kind():
    props = {'app_uuid': 'u', 'update_kind': 'reapply', 'active_question_groups': {'g': {'name': {'prompt': {}}}}}
    assert yc.form_context(_app_form_page(props))['updateKind'] == 'reapply'


def test_form_context_refuses_a_page_without_the_app_form():
    with pytest.raises(RuntimeError):
        yc.form_context(_app_form_page({'active_question_groups': {'g': {'name': {}}}}))
    with pytest.raises(RuntimeError):
        yc.form_context(_app_form_page({'app_uuid': 'u'}))
