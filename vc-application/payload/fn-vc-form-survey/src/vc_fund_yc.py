# The YC adapter of the vc-form-survey Function: how a survey signs in to YC, what it may send, and
# where the application form's state is.
#
# This file is NOT part of any bundle - see vc_http.py. One adapter per fund, loaded by name from
# vc_form_survey.ADAPTERS; a new fund is a new vc_fund_<fund>.py beside this one.
#
# YC's application (apply.ycombinator.com) sits behind YC's single sign-on (account.ycombinator.com). Both
# are Inertia.js apps (Rails + React + Vite, YC's "Bookface"): a page's whole state arrives as JSON in the
# data-page attribute of its root element, so a plain HTTP client reads what the React page renders from.
#
# THE SIGN-IN, as the SSO page's own client does it (sso-server and authorizedFetch bundles, read
# 2026-10-27):
#   GET  account.ycombinator.com/?continue=<form url>   cookies, and <meta name="csrf-token">
#   POST /start_sign_in {email | ycid, continue}         {mode, ycid?, requireYcid?}
#   POST /sign_in {ycid, password, continue}             200 {redirectTo}            - signed in
#                                                        200 {emailCode, ...}        - a new-device code was e-mailed
#                                                        non-200 {errors, captchaKey?, totpRequired?}
#   GET  redirectTo                                      back on apply.ycombinator.com, signed in
# Every POST carries X-CSRF-Token (the meta's value), X-Requested-With: XMLHttpRequest, a JSON body and
# the cookies. A 422 means the CSRF token was stale.
#
# WHAT A SURVEY MAY SEND (may_send): GET to any https host of ycombinator.com, and POST to exactly the two
# sign-in paths above on account.ycombinator.com. Nothing else - above all no write of any method to
# apply.ycombinator.com, so a survey can never change the application it reads. Each of the three steps
# YC may add to a sign-in - a reCAPTCHA, a two-factor code, an e-mailed code - needs a person, and each
# ends the survey with a message naming which one it was.

import html
import json
import re
import urllib.parse

FUND = 'yc'

ACCOUNT_ORIGIN = 'https://account.ycombinator.com'
ACCOUNT_HOST = 'account.ycombinator.com'
APPLY_HOST = 'apply.ycombinator.com'
YC_DOMAIN = 'ycombinator.com'

START_SIGN_IN_PATH = '/start_sign_in'
SIGN_IN_PATH = '/sign_in'
SIGN_IN_POSTS = (START_SIGN_IN_PATH, SIGN_IN_PATH)

CSRF_META = re.compile(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', re.I)
DATA_PAGE = re.compile(r'\sdata-page="([^"]*)"')


class SignInNeedsPerson(RuntimeError):
    """YC asked for something only a person can give: a reCAPTCHA, a two-factor code, an e-mailed code."""


# ---------------------------------------------------------------------------------------------------
# WHAT MAY BE SENT

def _is_yc_host(host):
    host = (host or '').lower()
    return host == YC_DOMAIN or host.endswith('.' + YC_DOMAIN)


def may_send(method, url):
    """True only for a GET to an https ycombinator.com host, or a POST to one of the two sign-in paths."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or not _is_yc_host(parts.hostname):
        return False
    if method == 'GET':
        return True
    return method == 'POST' and parts.hostname == ACCOUNT_HOST and parts.path in SIGN_IN_POSTS


def check_form_url(url):
    """The form url, stripped - or a refusal when it is not an https url on apply.ycombinator.com."""
    url = (url or '').strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or parts.hostname != APPLY_HOST or not parts.path.strip('/'):
        raise ValueError("formUrl must be an https url of a page on " + APPLY_HOST
                         + ", such as https://apply.ycombinator.com/apps/<id>/edit, got '" + url + "'")
    return url


# ---------------------------------------------------------------------------------------------------
# READING A PAGE

def csrf_token(page_html):
    m = CSRF_META.search(page_html or '')
    if not m:
        raise RuntimeError('the YC sign-in page carries no csrf-token meta - YC changed its page')
    return html.unescape(m.group(1))


def inertia_page(page_html):
    """The Inertia page object - {component, props, url, version} - from a page's data-page attribute."""
    m = DATA_PAGE.search(page_html or '')
    if not m:
        raise RuntimeError('the page carries no Inertia data-page attribute - YC changed its pages')
    try:
        page = json.loads(html.unescape(m.group(1)))
    except ValueError:
        raise RuntimeError('the data-page attribute is not JSON') from None
    if not isinstance(page, dict):
        raise RuntimeError('the data-page attribute is JSON but not an object')
    return page


def parse_answer(text, what):
    """A sign-in step's JSON answer as a dict; a body that is not a JSON object is a failure naming the step."""
    try:
        answer = json.loads(text)
    except ValueError:
        raise RuntimeError(what + ': YC answered with a body that is not JSON') from None
    if not isinstance(answer, dict):
        raise RuntimeError(what + ': YC answered with JSON that is not an object')
    return answer


def errors_text(answer):
    """YC's error messages, flattened. Never carries anything this Function sent - YC does not echo a password."""
    errors = answer.get('errors')
    if isinstance(errors, dict):
        return '; '.join(str(k) + ': ' + str(v) for k, v in errors.items())
    if errors:
        return str(errors)
    return str(answer.get('message') or '')


# ---------------------------------------------------------------------------------------------------
# THE SIGN-IN STEPS

def xhr_headers(token):
    return {'X-CSRF-Token': token, 'X-Requested-With': 'XMLHttpRequest'}


def start_sign_in_body(login, continue_url):
    """The SSO client sends an e-mail as 'email' and anything else as 'ycid'."""
    key = 'email' if '@' in login else 'ycid'
    return {key: login, 'continue': continue_url}


def identifier_after_start(status, answer, login):
    """The identifier /sign_in is to be sent, from /start_sign_in's answer - or a failure naming why there is none."""
    if status == 422:
        raise RuntimeError('start_sign_in: HTTP 422 - the CSRF token was refused')
    if status != 200:
        raise RuntimeError('start_sign_in: HTTP ' + str(status) + ': ' + errors_text(answer))
    mode = answer.get('mode')
    if mode == 'magic_link':
        raise SignInNeedsPerson('YC signs this login in by an e-mailed link only, not by password')
    if mode == 'sign_up':
        raise RuntimeError('YC knows no account for the login in the Vault entry')
    if answer.get('requireYcid'):
        raise RuntimeError('several YC accounts share this e-mail: the Vault entry must hold the YC username, '
                           'not the e-mail')
    return answer.get('ycid') or login


def sign_in_body(identifier, password, continue_url):
    return {'ycid': identifier, 'password': password, 'continue': continue_url}


def redirect_after_sign_in(status, answer):
    """Where /sign_in sends a signed-in client - or a failure naming what YC asked for instead."""
    if status == 200:
        if answer.get('emailCode'):
            raise SignInNeedsPerson('YC e-mailed a 6-digit code to the account (a new-device check) and waits '
                                    'for it - a person has to read the mailbox')
        if answer.get('redirectTo'):
            return str(answer['redirectTo'])
        raise RuntimeError('sign_in: HTTP 200 without a redirect')
    if answer.get('captchaKey'):
        raise SignInNeedsPerson('YC demands a reCAPTCHA before it accepts the password (HTTP ' + str(status) + ')')
    if answer.get('totpRequired'):
        raise SignInNeedsPerson('the account has two-factor sign-in: YC demands its code (HTTP ' + str(status) + ')')
    if status == 422:
        raise RuntimeError('sign_in: HTTP 422 - the CSRF token was refused')
    raise RuntimeError('sign_in: HTTP ' + str(status) + ': ' + (errors_text(answer) or 'no message'))


def _host(url):
    return urllib.parse.urlsplit(url).hostname


def _path(url):
    return urllib.parse.urlsplit(url).path.rstrip('/')


# ---------------------------------------------------------------------------------------------------
# THE SURVEY

def survey(session, login, password, form_url, log):
    """Sign in when YC asks for it, then read the form page. Returns {host, path, component, version, props}.

    session is a vc_http.Session opened with may_send above."""
    form_url = check_form_url(form_url)
    first = session.get(form_url)
    current = first
    if _host(first.url) == ACCOUNT_HOST:
        sign_in_page = inertia_page(first.text)
        log('YC shows ' + str(sign_in_page.get('component')) + ' - signing in')
        token = csrf_token(first.text)
        continue_url = (sign_in_page.get('props') or {}).get('continue') or form_url
        start = session.post_json(ACCOUNT_ORIGIN + START_SIGN_IN_PATH, start_sign_in_body(login, continue_url),
                                  xhr_headers(token))
        identifier = identifier_after_start(start.status, parse_answer(start.text, 'start_sign_in'), login)
        answer = session.post_json(ACCOUNT_ORIGIN + SIGN_IN_PATH, sign_in_body(identifier, password, continue_url),
                                   xhr_headers(token))
        redirect_to = redirect_after_sign_in(answer.status, parse_answer(answer.text, 'sign_in'))
        log('signed in')
        current = session.get(urllib.parse.urljoin(ACCOUNT_ORIGIN, redirect_to))
        if _host(current.url) != APPLY_HOST or _path(current.url) != _path(form_url):
            current = session.get(form_url)
    if current.status != 200:
        raise RuntimeError('the form page answered HTTP ' + str(current.status))
    if _host(current.url) != APPLY_HOST:
        raise RuntimeError('after the sign-in YC still shows a page on ' + str(_host(current.url))
                           + ', not the form on ' + APPLY_HOST)
    page = inertia_page(current.text)
    return {
        'host': _host(current.url),
        'path': urllib.parse.urlsplit(current.url).path,
        'component': page.get('component'),
        'version': page.get('version'),
        'props': page.get('props'),
    }
