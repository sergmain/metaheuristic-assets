# Unit tests of the generic core of vc_form_survey.py. Every input is built here; nothing is read from a
# fund's site, a Vault or MH (MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md section 5).

import json

import pytest

import vc_form_survey as s


# --- the credential --------------------------------------------------------------------------------

def test_split_credential_plain():
    assert s.split_credential(bytearray(b'founder@example.com:secret')) == ('founder@example.com', 'secret')


def test_split_credential_password_may_contain_colons():
    assert s.split_credential(bytearray(b'founder:se:cr:et')) == ('founder', 'se:cr:et')


def test_split_credential_drops_trailing_line_break():
    assert s.split_credential(bytearray(b'founder:secret\r\n')) == ('founder', 'secret')


def test_split_credential_without_colon_is_refused_and_not_echoed():
    with pytest.raises(ValueError) as e:
        s.split_credential(bytearray(b'founder-secret'))
    assert 'no colon' in str(e.value)
    assert 'founder-secret' not in str(e.value)


def test_split_credential_empty_login_is_refused():
    with pytest.raises(ValueError) as e:
        s.split_credential(bytearray(b':secret'))
    assert 'empty login' in str(e.value)
    assert 'secret' not in str(e.value).replace('(the value is not printed)', '')


def test_split_credential_empty_password_is_refused():
    with pytest.raises(ValueError) as e:
        s.split_credential(bytearray(b'founder:'))
    assert 'empty password' in str(e.value)


# --- the adapter registry --------------------------------------------------------------------------

def test_load_adapter_imports_the_registered_module():
    imported = []
    module = s.load_adapter('yc', lambda name: imported.append(name) or name)
    assert imported == ['vc_fund_yc']
    assert module == 'vc_fund_yc'


def test_load_adapter_yc_is_the_yc_module():
    assert s.load_adapter('yc').FUND == 'yc'


def test_load_adapter_unknown_fund_names_the_known_ones():
    with pytest.raises(ValueError) as e:
        s.load_adapter('a16z')
    assert "'a16z'" in str(e.value)
    assert "['yc']" in str(e.value)


# --- extracting fields -----------------------------------------------------------------------------

PROPS = {
    'app': {'id': 'f00d', 'status': 'draft'},
    'sections': [
        {'title': 'Company', 'slug': 'company', 'questions': [
            {'key': 'company_name', 'label': 'Company name', 'type': 'text', 'required': True, 'max_length': 60},
            {'key': 'company_url', 'label': 'Company url, if any', 'type': 'url', 'required': False},
        ]},
        {'title': 'Progress', 'slug': 'progress', 'questions': [
            {'key': 'stage', 'question': 'How far along are you?', 'kind': 'select',
             'options': [{'value': 'idea', 'label': 'Just an idea'}, {'value': 'live', 'label': 'Live'}]},
            {'id': 4471, 'prompt': 'Why now?', 'input_type': 'textarea', 'optional': True, 'word_limit': 250},
        ]},
    ],
    'answers': {'company_name': 'Acme Rockets', 'stage': 'idea'},
}


def test_extract_fields_finds_every_field_in_document_order():
    fields = s.extract_fields(PROPS)
    assert [f['key'] for f in fields] == ['company_name', 'company_url', 'stage', '4471']


def test_extract_fields_reads_label_type_required_limits():
    first = s.extract_fields(PROPS)[0]
    assert first['label'] == 'Company name'
    assert first['type'] == 'text'
    assert first['required'] is True
    assert first['limits'] == {'max_length': 60}
    assert first['path'] == 'props.sections[0].questions[0]'


def test_extract_fields_optional_flag_means_not_required():
    why_now = s.extract_fields(PROPS)[3]
    assert why_now['required'] is False
    assert why_now['limits'] == {'word_limit': 250}
    assert why_now['type'] == 'textarea'


def test_extract_fields_required_unknown_is_none():
    assert s.extract_fields(PROPS)[2]['required'] is None


def test_extract_fields_options_are_choices_not_fields():
    stage = s.extract_fields(PROPS)[2]
    assert stage['options'] == [{'value': 'idea', 'label': 'Just an idea'}, {'value': 'live', 'label': 'Live'}]


def test_extract_fields_a_container_is_a_section_not_a_field():
    fields = s.extract_fields(PROPS)
    assert [f['section'] for f in fields] == ['Company', 'Company', 'Progress', 'Progress']


def test_extract_fields_no_definitions_is_empty():
    assert s.extract_fields({'app': {'company_name': 'Acme'}, 'flash': {}}) == []


def test_extract_fields_label_without_identity_is_not_a_field():
    assert s.extract_fields({'q': [{'label': 'Company name', 'value': 'Acme'}]}) == []


# --- variable names and the variables block --------------------------------------------------------

def test_variable_name_snake_camel_and_numeric():
    assert s.variable_name('yc', 'company_name') == 'ycCompanyName'
    assert s.variable_name('yc', 'companyUrl') == 'ycCompanyUrl'
    assert s.variable_name('yc', '4471') == 'ycField4471'
    assert s.variable_name('yc', 'founders[0].email') == 'ycFounders0Email'


def test_assign_variable_names_suffixes_a_taken_name():
    fields = [{'key': 'company_name'}, {'key': 'company-name'}, {'key': 'company.name'}]
    assert [f['variable'] for f in s.assign_variable_names('yc', fields)] == \
        ['ycCompanyName', 'ycCompanyName2', 'ycCompanyName3']


def test_variables_block_one_input_per_field_nullable_unless_required():
    fields = s.assign_variable_names('yc', s.extract_fields(PROPS))
    assert s.variables_block(fields) == (
        'variables {\n'
        '    // Company name (text, required)\n'
        '    <- ycCompanyName\n'
        '    // Company url, if any (url, optional)\n'
        '    <- ycCompanyUrl?\n'
        '    // How far along are you? (select, required unknown)\n'
        '    <- ycStage?\n'
        '    // Why now? (textarea, optional)\n'
        '    <- ycField4471?\n'
        '}\n')


def test_variables_block_no_fields_is_an_empty_block():
    assert s.variables_block([]) == 'variables {\n}\n'


# --- the skeleton carries no applicant content -----------------------------------------------------

def test_skeleton_redacts_answers_and_keeps_definitions():
    text = json.dumps(s.skeleton(PROPS))
    assert 'Acme Rockets' not in text
    assert 'Company name' in text
    assert 'Just an idea' in text
    assert 'company_name' in text


def test_skeleton_answer_string_becomes_its_length():
    assert s.skeleton({'answers': {'company_name': 'Acme Rockets'}}) == {'answers': {'company_name': 'str:12'}}


def test_skeleton_identity_shown_only_when_identifier_shaped():
    assert s.skeleton({'name': 'company_name'}) == {'name': 'company_name'}
    assert s.skeleton({'name': 'Jane Q. Founder'}) == {'name': 'str:15'}


def test_skeleton_list_shows_length_and_first_items():
    assert s.skeleton({'tags': ['a', 'b', 'c', 'd']}) == {'tags': {'#': 4, 'items': ['str:1', 'str:1', 'str:1']}}


def test_skeleton_numbers_kept_only_as_limits_or_ids():
    assert s.skeleton({'max_length': 60, 'id': 7, 'equity': 7.5}) == {'max_length': 60, 'id': 7, 'equity': 'number'}


# --- the inventory ---------------------------------------------------------------------------------

def test_inventory_counts_the_fields_it_lists():
    fields = s.assign_variable_names('yc', s.extract_fields(PROPS))
    page = {'host': 'apply.example', 'path': '/apps/x/edit', 'component': 'Apps/Edit', 'version': 'v1', 'props': PROPS}
    inv = s.inventory('yc', page, fields)
    assert inv['fieldCount'] == 4 == len(inv['fields'])
    assert inv['form'] == {'host': 'apply.example', 'path': '/apps/x/edit', 'component': 'Apps/Edit', 'version': 'v1'}
    assert 'Acme Rockets' not in json.dumps(inv)
