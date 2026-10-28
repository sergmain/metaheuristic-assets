# Unit tests of the YC adapter, vc_fund_yc.py. Every input is built here, in the format YC's pages and
# answers have (the sign-in page read 2026-10-27: an HTML-escaped data-page attribute, a csrf-token meta);
# nothing is sent to YC.

import html
import json

import pytest

import vc_fund_yc as yc

FORM_URL = 'https://apply.ycombinator.com/apps/00000000-0000-0000-0000-000000000000/edit'


# --- what a survey may send -----------------------------------------------------------------------

def test_may_send_get_to_both_yc_hosts():
    assert yc.may_send('GET', FORM_URL)
    assert yc.may_send('GET', 'https://account.ycombinator.com/?continue=x')
    assert yc.may_send('GET', 'https://bookface-static.ycombinator.com/vite/assets/a.js')


def test_may_send_post_only_to_the_two_sign_in_paths():
    assert yc.may_send('POST', 'https://account.ycombinator.com/start_sign_in')
    assert yc.may_send('POST', 'https://account.ycombinator.com/sign_in')
    assert not yc.may_send('POST', 'https://account.ycombinator.com/sign_in/email_code')
    assert not yc.may_send('POST', 'https://account.ycombinator.com/sign_up')
    assert not yc.may_send('POST', 'https://account.ycombinator.com/verify_otp')


def test_may_send_never_writes_to_the_application():
    for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        assert not yc.may_send(method, FORM_URL), method
        assert not yc.may_send(method, 'https://apply.ycombinator.com/sign_in'), method


def test_may_send_refuses_other_hosts_and_plain_http():
    assert not yc.may_send('GET', 'http://apply.ycombinator.com/apps/x/edit')
    assert not yc.may_send('GET', 'https://evilycombinator.com/')
    assert not yc.may_send('GET', 'https://ycombinator.com.example.org/')
    assert not yc.may_send('GET', 'https://example.org/')


def test_check_form_url_accepts_an_apply_page_and_strips_it():
    assert yc.check_form_url('  ' + FORM_URL + '\n') == FORM_URL


def test_check_form_url_refuses_other_hosts_plain_http_and_the_root():
    for url in ('https://account.ycombinator.com/apps/x/edit', 'http://apply.ycombinator.com/apps/x/edit',
                'https://apply.ycombinator.com/', 'not a url', ''):
        with pytest.raises(ValueError):
            yc.check_form_url(url)


# --- reading a page -------------------------------------------------------------------------------

def page_html(page, csrf='tok-123'):
    """A page in the format YC serves: a csrf-token meta and an HTML-escaped data-page attribute."""
    return ('<!DOCTYPE html><html><head><meta name="csrf-param" content="authenticity_token" />\n'
            '<meta name="csrf-token" content="' + csrf + '" /></head><body>\n'
            '<div id="app" data-page="' + html.escape(json.dumps(page), quote=True) + '"></div></body></html>')


SIGN_IN_PAGE = {'component': 'SignIn', 'props': {'showLinkedin': True, 'continue': FORM_URL},
                'url': '/?continue=x', 'version': 'abc'}


def test_csrf_token_from_the_meta():
    assert yc.csrf_token(page_html(SIGN_IN_PAGE, 'Zx+/=9')) == 'Zx+/=9'


def test_csrf_token_absent_is_a_failure():
    with pytest.raises(RuntimeError):
        yc.csrf_token('<html></html>')


def test_inertia_page_unescapes_the_data_page():
    assert yc.inertia_page(page_html(SIGN_IN_PAGE)) == SIGN_IN_PAGE


def test_inertia_page_keeps_quotes_and_ampersands_inside_strings():
    page = {'component': 'Apps/Edit', 'props': {'q': 'Why "now" & not later? <b>'}}
    assert yc.inertia_page(page_html(page)) == page


def test_inertia_page_absent_is_a_failure():
    with pytest.raises(RuntimeError):
        yc.inertia_page('<html><div id="app"></div></html>')


# --- the sign-in steps ----------------------------------------------------------------------------

def test_start_sign_in_body_email_or_username():
    assert yc.start_sign_in_body('founder@example.com', FORM_URL) == {'email': 'founder@example.com', 'continue': FORM_URL}
    assert yc.start_sign_in_body('founder', FORM_URL) == {'ycid': 'founder', 'continue': FORM_URL}


def test_identifier_after_start_takes_the_resolved_ycid():
    assert yc.identifier_after_start(200, {'mode': 'password', 'ycid': 'founder'}, 'founder@example.com') == 'founder'


def test_identifier_after_start_falls_back_to_the_login():
    assert yc.identifier_after_start(200, {}, 'founder@example.com') == 'founder@example.com'


def test_identifier_after_start_magic_link_needs_a_person():
    with pytest.raises(yc.SignInNeedsPerson):
        yc.identifier_after_start(200, {'mode': 'magic_link'}, 'founder@example.com')


def test_identifier_after_start_unknown_account():
    with pytest.raises(RuntimeError) as e:
        yc.identifier_after_start(200, {'mode': 'sign_up'}, 'founder@example.com')
    assert 'no account' in str(e.value)


def test_identifier_after_start_shared_email_needs_the_username():
    with pytest.raises(RuntimeError) as e:
        yc.identifier_after_start(200, {'mode': 'password', 'requireYcid': True}, 'founder@example.com')
    assert 'username' in str(e.value)


def test_identifier_after_start_refusal_carries_yc_errors():
    with pytest.raises(RuntimeError) as e:
        yc.identifier_after_start(400, {'errors': {'ycid': 'is invalid'}}, 'x')
    assert 'ycid: is invalid' in str(e.value)


def test_redirect_after_sign_in_signed_in():
    assert yc.redirect_after_sign_in(200, {'redirectTo': '/sso?x=1'}) == '/sso?x=1'


def test_redirect_after_sign_in_email_code_needs_a_person():
    with pytest.raises(yc.SignInNeedsPerson) as e:
        yc.redirect_after_sign_in(200, {'emailCode': True, 'authenticityToken': 't'})
    assert 'e-mailed' in str(e.value)


def test_redirect_after_sign_in_captcha_needs_a_person():
    with pytest.raises(yc.SignInNeedsPerson) as e:
        yc.redirect_after_sign_in(401, {'captchaKey': 'site-key', 'errors': {'general': 'x'}})
    assert 'reCAPTCHA' in str(e.value)


def test_redirect_after_sign_in_two_factor_needs_a_person():
    with pytest.raises(yc.SignInNeedsPerson) as e:
        yc.redirect_after_sign_in(401, {'totpRequired': True})
    assert 'two-factor' in str(e.value)


def test_redirect_after_sign_in_wrong_password_carries_yc_errors():
    with pytest.raises(RuntimeError) as e:
        yc.redirect_after_sign_in(401, {'errors': {'password': 'is incorrect'}})
    assert 'password: is incorrect' in str(e.value)
    assert not isinstance(e.value, yc.SignInNeedsPerson)


def test_sign_in_body_has_exactly_the_fields_the_sso_client_sends():
    assert yc.sign_in_body('founder', 'pw', FORM_URL) == {'ycid': 'founder', 'password': 'pw', 'continue': FORM_URL}


def test_parse_answer_refuses_html():
    with pytest.raises(RuntimeError) as e:
        yc.parse_answer('<html>Just a moment</html>', 'sign_in')
    assert 'sign_in' in str(e.value)


# --- the fields: questionLabels ------------------------------------------------------------------

EDIT_PROPS = {
    'app': {'uuid': 'u-1', 'questions': {'describe': 'We build rockets', 'url': 'https://acme.example'}},
    'questionLabels': {
        'describe': {'q': 'Describe what your company does in 50 characters or less.'},
        'url': {'q': 'Company URL, if any', 'placeholder': 'https://'},
        'demo': {'q': 'If you have a demo, what is the url?', 'subtitle': 'For example, a video of the product.'},
        'tools': {'subtitle': 'Which AI tools do you use?'},
        'legacy': 'Old-style label as a plain string',
    },
    'activeQuestionGroups': {'Company': {'describe': True, 'url': True}, 'Progress': ['demo']},
}


def test_extract_fields_one_per_question_label_in_server_order():
    assert [f['key'] for f in yc.extract_fields(EDIT_PROPS)] == ['describe', 'url', 'demo', 'tools', 'legacy']


def test_extract_fields_label_help_and_section():
    fields = {f['key']: f for f in yc.extract_fields(EDIT_PROPS)}
    assert fields['describe']['label'] == 'Describe what your company does in 50 characters or less.'
    assert fields['describe']['section'] == 'Company'
    assert fields['url']['help'] == 'https://'
    assert fields['demo']['help'] == 'For example, a video of the product.'
    assert fields['demo']['section'] == 'Progress'
    assert fields['tools']['label'] == 'Which AI tools do you use?'
    assert fields['tools']['help'] is None
    assert fields['legacy']['label'] == 'Old-style label as a plain string'
    assert fields['legacy']['section'] is None


def test_extract_fields_type_required_options_stay_unknown():
    f = yc.extract_fields(EDIT_PROPS)[0]
    assert (f['type'], f['required'], f['options'], f['limits']) == (None, None, None, None)
    assert f['path'] == 'props.questionLabels.describe'


def test_extract_fields_never_carries_the_answers():
    text = json.dumps(yc.extract_fields(EDIT_PROPS))
    assert 'We build rockets' not in text
    assert 'acme.example' not in text


def test_extract_fields_found_inside_a_pushed_component():
    combined = {'components': [{'component': 'Nav', 'props': {}}, {'component': 'Edit', 'props': EDIT_PROPS}]}
    assert len(yc.extract_fields(combined)) == 5


def test_extract_fields_without_question_labels_is_empty():
    assert yc.extract_fields({'app': {'questions': {'describe': 'x'}}}) == []
    assert yc.extract_fields(None) == []
