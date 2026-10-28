# YC's application form as the apply page really carries it (E4, ExecContext #5319, 2026-10-27): the AppForm push's
# props hold active_question_groups = {group: {fieldName: {prompt: {q, required, subtitle?, placeholder?} | null}}} -
# the question definitions, keyed by field name, grouped as the form shows them. No questionLabels prop exists on the
# page. The content below is invented; the shape is the observed one.

import vc_fund_yc as yc
import vc_form_survey as s

APP_FORM_PAGE_PROPS = {'components': [
    {'component': 'components/Header', 'props': {'loggedIn': True, 'chatEnabled': False}},
    {'component': 'components/AppForm', 'props': {
        'user_hnid': 'founder1',
        'app_uuid': '00000000-0000-0000-0000-000000000000',
        'update_kind': None,
        'future_batch_names': ['Summer 2027'],
        'active_question_groups': {
            'Founders': {
                'founderBios': {'prompt': None},
                'meet': {'prompt': {'q': 'How did you meet?', 'required': False}},
            },
            'Company': {
                'name': {'prompt': {'q': 'Company name', 'required': True}},
                'url': {'prompt': {'q': 'Company URL, if any', 'placeholder': 'https://', 'required': False}},
            },
            'Idea': {
                'money': {'prompt': {'q': 'How will you make money?', 'subtitle': '(best estimate)', 'required': False}},
            },
        },
    }},
    {'component': 'components/Footer', 'props': {}},
]}


def test_extract_fields_reads_active_question_groups():
    fields = yc.extract_fields(APP_FORM_PAGE_PROPS)
    assert [f['key'] for f in fields] == ['founderBios', 'meet', 'name', 'url', 'money']
    assert [f['label'] for f in fields] == [None, 'How did you meet?', 'Company name', 'Company URL, if any',
                                           'How will you make money?']
    assert [f['required'] for f in fields] == [None, False, True, False, False]
    assert [f['help'] for f in fields] == [None, None, None, 'https://', '(best estimate)']
    assert [f['section'] for f in fields] == ['Founders', 'Founders', 'Company', 'Company', 'Idea']
    assert fields[0]['path'] == 'props.active_question_groups.Founders.founderBios'
    assert all(f['type'] is None and f['options'] is None and f['limits'] is None for f in fields)


def test_extract_fields_never_reads_the_rest_of_the_app_form_props():
    text = str(yc.extract_fields(APP_FORM_PAGE_PROPS))
    assert 'founder1' not in text
    assert '00000000-0000' not in text
    assert 'Summer 2027' not in text


def test_variables_block_field_without_a_label():
    fields = s.assign_variable_names('yc', [{'key': 'founderBios', 'label': None, 'type': None, 'required': None}])
    assert s.variables_block(fields) == ('variables {\n    // (no label on the form) (type unknown, required unknown)\n'
                                         '    <- ycFounderBios?\n}\n')
