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
# THE FIELDS
#
# OBSERVED (E4, ExecContext #5319, 2026-10-27): the AppForm push's props carry active_question_groups =
# {group: {fieldName: {prompt: {q, required, subtitle?, placeholder?} | null}}} - every question of the form with its
# label and required flag, grouped as the form shows them - and NO questionLabels; AppForm builds its labels from
# prompt.q (apply-*.js). That is read first. The paragraph below is the earlier reading, kept for a page that carries
# questionLabels instead.
#
# What the apply bundle reads (apply-*.js, read 2026-10-27): every question is a field component (InputField,
# TextareaField, SelectField, Radio, CheckboxField, VideoField, ...) named by a fieldName literal in the bundle, and it
# takes its label from questionLabels[fieldName] = {q, subtitle, placeholder}. The application form renders with
# hideQuestionsWithoutLabels: a question with no entry in questionLabels is not shown. So the server's
# questionLabels - a prop of the page - IS the set of fields this batch's form shows, in the server's order. The
# answers are app.questions[fieldName] and are never read here. Types, required flags and choices are defined in the
# bundle's code, not in the props, so they stay unknown (None).

LABEL_MAX = 300


def _one_line(text, limit=LABEL_MAX):
    text = ' '.join(str(text).split())
    return text if len(text) <= limit else text[:limit] + '...'


def find_key(value, name):
    """The first value under key name anywhere in a JSON tree, depth-first in document order; None when absent."""
    if isinstance(value, dict):
        if name in value:
            return value[name]
        for v in value.values():
            found = find_key(v, name)
            if found is not None:
                return found
    elif isinstance(value, list):
        for v in value:
            found = find_key(v, name)
            if found is not None:
                return found
    return None


def _sections(groups):
    """fieldName -> question group, from activeQuestionGroups ({group: {fieldName: ...}} or {group: [fieldName]})."""
    section_of = {}
    if isinstance(groups, dict):
        for group, members in groups.items():
            names = members.keys() if isinstance(members, dict) else members if isinstance(members, list) else []
            for name in names:
                if isinstance(name, str):
                    section_of.setdefault(name, group)
    return section_of


def _text(value):
    return value if isinstance(value, str) and value.strip() else None


def fields_from_question_groups(groups):
    """One field per entry of the server's active_question_groups - {group: {fieldName: {prompt: {q, required, subtitle?,
    placeholder?} | null}}} - in the server's order, the group as its section. A null prompt (founderBios: the founders'
    profiles, a form of their own) is a field with no label. Nothing but the prompt of each entry is read."""
    fields = []
    for group, members in groups.items():
        if not isinstance(members, dict):
            continue
        for key, entry in members.items():
            prompt = entry.get('prompt') if isinstance(entry, dict) else None
            prompt = prompt if isinstance(prompt, dict) else {}
            q = _text(prompt.get('q'))
            subtitle = _text(prompt.get('subtitle'))
            placeholder = _text(prompt.get('placeholder'))
            label = q or subtitle
            help_text = subtitle if q and subtitle else placeholder
            fields.append({
                'key': key,
                'label': _one_line(label) if label else None,
                'type': None,
                'required': prompt.get('required') if isinstance(prompt.get('required'), bool) else None,
                'options': None,
                'limits': None,
                'help': _one_line(help_text) if help_text else None,
                'section': group,
                'path': 'props.active_question_groups.' + str(group) + '.' + str(key),
            })
    return fields


def extract_fields(props):
    """The form's fields: from active_question_groups when the props carry it (YC's AppForm - E4, ExecContext #5319),
    else one field per questionLabels entry, in the server's order; [] when neither is there (the core then falls back
    to its generic extraction)."""
    groups = find_key(props, 'active_question_groups')
    if isinstance(groups, dict) and groups:
        return fields_from_question_groups(groups)
    labels = find_key(props, 'questionLabels')
    if not isinstance(labels, dict) or not labels:
        return []
    section_of = _sections(find_key(props, 'activeQuestionGroups'))
    fields = []
    for key, entry in labels.items():
        entry = entry if isinstance(entry, dict) else ({'q': entry} if isinstance(entry, str) else {})
        q = entry.get('q') if isinstance(entry.get('q'), str) and entry.get('q').strip() else None
        subtitle = entry.get('subtitle') if isinstance(entry.get('subtitle'), str) and entry.get('subtitle').strip() else None
        placeholder = entry.get('placeholder') if isinstance(entry.get('placeholder'), str) else None
        label = q or subtitle or key
        help_text = subtitle if q and subtitle else placeholder
        fields.append({
            'key': key,
            'label': _one_line(label),
            'type': None,
            'required': None,
            'options': None,
            'limits': None,
            'help': _one_line(help_text) if help_text and help_text.strip() else None,
            'section': section_of.get(key),
            'path': 'props.questionLabels.' + key,
        })
    return fields


# ---------------------------------------------------------------------------------------------------
# THE SURVEY
#
# E1 (ExecContext #5156, 2026-10-27): the sign-in above went through over plain HTTP - /start_sign_in and /sign_in
# both HTTP 200, no reCAPTCHA, no two-factor code, no e-mailed code - and the form page answered HTTP 200 on
# apply.ycombinator.com.

def survey(session, login, password, form_url, log):
    """Sign in when YC asks for it, then fetch the form page. Returns {host, path, html}.

    The SSO's sign-in page is Inertia and is read here; the form page is handed back as HTML and read by the core
    (vc_page.py), because what it embeds is not the SSO's format - E1, ExecContext #5156: the signed-in form page on
    apply.ycombinator.com carries no Inertia data-page attribute.

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
    return {
        'host': _host(current.url),
        'path': urllib.parse.urlsplit(current.url).path,
        'html': current.text,
    }


# ---------------------------------------------------------------------------------------------------
# THE APPLY (mh.asset.vc-apply-yc, vc_apply.py) - read the application's answers, save the ones that differ
#
# How YC's page reads and saves an application (apply-*.js, read 2026-10-30 and 2026-11-02, no credential):
#   - one Apollo client on POST /graphql of apply.ycombinator.com: the session's cookies, and the header
#     X-CSRF-Token = the page's <meta name="csrf-token">; on HTTP 422 it retries once with a fresh token
#   - SHOW_APP($appUuid) -> app { ...AppFragment }: the answers are app.questions (AppQuestions - one field per
#     question; revenueamount is a list of {val, month})
#   - UPDATE_APP($uuid, $input: UpdateAppInput!, $reloadApp) -> updateApp { success persisted errors app {...} }. The
#     page's Lw(...) builds input = {questions: <only the questions whose value changed>, ...}: an autosave adds
#     autosave: 1 and no applicantsAttributes; a regular save adds applicantsAttributes (co-founder invites); a submit
#     adds submitOnSave: 1 and sends every question; updateKind is the AppForm's update_kind prop when it has one
#   - videoS3Key / demoS3Key are multipart uploads (CREATE_APP_VIDEO, SIGN_APP_VIDEO_PART, COMPLETE_APP_VIDEO) and App
#     fields, not questions; founderBios is each founder's profile (UPDATE_BIO); codingAgentSession is an upload
#   - choice values (the MC / PC components): stage '1' (not used yet - whenbeta follows) | '2' (used - usernums
#     follows); revenue, incyet, investyet, currentlyraising 'yes' | 'no'; batchPreference 'current' | 'future'.
#     Shown only on a path: meet with more than one founder; inctype / incpercent when incyet is 'yes', percent2 when
#     'no'; incinvest, investamount, bank, burn, runway when investyet is 'yes'; raisingdetails when currentlyraising
#     is 'yes'; futureBatchName / futureBatchWhy when batchPreference is 'future'
#
# An apply saves the way the page's autosave does - the changed questions only, autosave: 1, no applicantsAttributes,
# never submitOnSave: the application is filled, never submitted. What it may send: what a survey may, plus POST to
# /graphql on apply.ycombinator.com (may_send_apply); which GraphQL operation is sent is decided per run - SHOW_APP
# always, UPDATE_APP only in production (graphql_body).

GRAPHQL_PATH = '/graphql'
APPLY_ORIGIN = 'https://' + APPLY_HOST

READ_OPS = ('SHOW_APP',)
WRITE_OPS = ('UPDATE_APP',)

# questions of the form that are not AppQuestions fields: uploads held by the App, and the founders' own profiles
NOT_QUESTIONS = ('videoS3Key', 'demoS3Key', 'founderBios')
# what an apply never writes: the above, the coding-agent upload, and the one question whose value is not a string
NOT_WRITABLE = NOT_QUESTIONS + ('codingAgentSession', 'revenueamount')

# Every field of YC's AppQuestions type, as the page's AppQuestionsFragment selects it (apply-*.js, read 2026-11-02).
# E1 of the apply (ExecContext #7433): the form's prompts include 'video' and 'demo', which are NOT AppQuestions fields -
# SHOW_APP refused them ('Field ... doesn't exist on type AppQuestions'), and the edit page renders neither. So a read
# selects only the form's questions that are listed here, and a question outside this list is never written.
APP_QUESTIONS = (
    'acc', 'name', 'url', 'describe', 'productLink', 'productCreds', 'make', 'where', 'wherewhy', 'howfar', 'worked',
    'techstack', 'codingAgentSession', 'stage', 'whenbeta', 'usernums', 'revenue', 'revenueamount', 'revenuesource',
    'growthrate', 'since', 'exp', 'get', 'money', 'category', 'citizenships', 'science', 'nextStages', 'byDd', 'fda',
    'expData', 'ideas', 'ip2', 'material', 'incyet', 'inctype', 'incpercent', 'percent2', 'investyet', 'incinvest',
    'investamount', 'burn', 'bank', 'runway', 'currentlyraising', 'raisingdetails', 'whyapply', 'howhear', 'referralCode',
    'meet', 'cofounder', 'others2', 'useracq', 'market', 'others', 'numFounders', 'resumes', 'edu', 'built', 'hack',
    'ability', 'distrac', 'commit', 'plans', 'whyno', 'movers', 'offer', 'ip', 'inc', 'percent', 'badness', 'sched',
    'metrics', 'compet', 'govgrant', 'margins', 'howmuch1', 'howmuch2', 'howmuch3', 'howmuch4', 'howmuch5', 'howmuch6',
    'new', 'proxy', 'program', 'rfsask', 'rfs', 'rfs2', 'rfs3', 'distro', 'buy', 'academic', 'exfactory', 'offShelf',
    'pat', 'hard', 'tools', 'wrong', 'extras', 'amuse', 'batchPreference', 'futureBatchName', 'futureBatchWhy',
)

CHOICES = {
    'stage': ('1', '2'),
    'revenue': ('yes', 'no'),
    'incyet': ('yes', 'no'),
    'investyet': ('yes', 'no'),
    'currentlyraising': ('yes', 'no'),
    'batchPreference': ('current', 'future'),
}
# the form's own words: "Describe what your company does in 50 characters or less."
LIMITS = {'describe': 50}

APP_STATUS_FIELDS = ('uuid', 'submitted', 'submittedAt', 'editable', 'fullEditable', 'status', 'batch', 'currentBatch',
                     'batchShortName', 'batchLongName', 'videoS3Key', 'demoS3Key', 'agentFilledQuestions')


class OperationRefused(RuntimeError):
    """A GraphQL operation this run may not send - a write outside production, or an operation nobody listed."""


def may_send_apply(method, url):
    """What a survey may send, plus a POST to /graphql on apply.ycombinator.com over https."""
    if may_send(method, url):
        return True
    parts = urllib.parse.urlsplit(url)
    return (method == 'POST' and parts.scheme == 'https' and parts.hostname == APPLY_HOST
            and parts.path == GRAPHQL_PATH)


def readable_keys(form_keys):
    """The AppQuestions fields a read selects: the form's questions that AppQuestions declares, in the form's order
    (E1, ExecContext #7433: 'video' and 'demo' are prompts of the form but no AppQuestions fields)."""
    return [k for k in form_keys if k in APP_QUESTIONS and k not in NOT_QUESTIONS]


def _selection(keys, indent):
    pad = ' ' * indent
    return '\n'.join(pad + k + (' {\n' + pad + '  val\n' + pad + '  month\n' + pad + '}' if k == 'revenueamount' else '')
                     for k in keys)


def show_app_query(keys):
    """SHOW_APP with this run's selection: the App's status fields and every question in keys."""
    return ('query SHOW_APP($appUuid: Uuid) {\n  app(uuid: $appUuid) {\n'
            + '\n'.join('    ' + f for f in APP_STATUS_FIELDS)
            + '\n    questions {\n' + _selection(keys, 6) + '\n    }\n  }\n}\n')


def update_app_mutation(keys):
    """UPDATE_APP, answering with the App's submitted flag and every question in keys."""
    return ('mutation UPDATE_APP($uuid: Uuid!, $input: UpdateAppInput!, $reloadApp: Boolean) {\n'
            '  updateApp(uuid: $uuid, input: $input, reloadApp: $reloadApp) {\n    success\n    persisted\n    errors\n'
            '    app {\n      uuid\n      submitted\n      questions {\n' + _selection(keys, 8) + '\n      }\n    }\n  }\n}\n')


def update_input(patch, update_kind):
    """The UpdateAppInput of a save as the page's autosave builds it: the changed questions, autosave 1, the form's
    updateKind when it has one - never applicantsAttributes, never submitOnSave."""
    if not patch:
        raise ValueError('an empty patch is never sent')
    payload = {'questions': dict(patch), 'autosave': 1}
    if update_kind:
        payload['updateKind'] = update_kind
    return payload


def graphql_body(op, query, variables, allowed_ops):
    """The /graphql request body - or a refusal when op is not allowed in this run, or the text is not that op."""
    if op not in allowed_ops or op not in READ_OPS + WRITE_OPS:
        raise OperationRefused('GraphQL operation ' + str(op) + ' is not allowed in this run (allowed: '
                               + ', '.join(allowed_ops) + ')')
    expected = ('mutation ' if op in WRITE_OPS else 'query ') + op + '('
    if not query.lstrip().startswith(expected):
        raise OperationRefused('the text sent as ' + op + ' does not start with "' + expected + '"')
    return {'operationName': op, 'variables': variables, 'query': query}


def form_context(page_html):
    """What an apply reads from the signed-in form page: the CSRF token, the AppForm's app_uuid, update_kind and its
    question keys (active_question_groups, in the form's order), and future_batch_names."""
    from vc_page import embedded_state

    _, state = embedded_state(page_html)
    props = state.get('props') if state else None
    app_uuid = find_key(props, 'app_uuid') if props else None
    groups = find_key(props, 'active_question_groups') if props else None
    if not isinstance(app_uuid, str) or not app_uuid.strip():
        raise RuntimeError('the form page carries no AppForm app_uuid - YC changed its page')
    if not isinstance(groups, dict) or not groups:
        raise RuntimeError('the form page carries no active_question_groups - YC changed its page')
    keys = [k for members in groups.values() if isinstance(members, dict) for k in members]
    update_kind = find_key(props, 'update_kind')
    return {
        'csrf': csrf_token(page_html),
        'appUuid': app_uuid,
        'updateKind': update_kind if isinstance(update_kind, str) and update_kind.strip() else None,
        'formKeys': keys,
        'futureBatchNames': find_key(props, 'future_batch_names'),
    }


def graphql_errors_text(errors):
    if isinstance(errors, list):
        return '; '.join(str(e.get('message') if isinstance(e, dict) else e) for e in errors)
    return str(errors)


def graphql(session, ctx, op, query, variables, allowed_ops, form_url, log):
    """One GraphQL operation as the page's Apollo client sends it; data, or a failure naming the operation."""
    body = graphql_body(op, query, variables, allowed_ops)
    headers = {'X-CSRF-Token': ctx['csrf'], 'Origin': APPLY_ORIGIN, 'Referer': check_form_url(form_url)}
    answer = session.post_json(APPLY_ORIGIN + GRAPHQL_PATH, body, headers)
    if answer.status == 422:
        log(op + ': HTTP 422 - the CSRF token was refused; reading a fresh one from the form page')
        ctx['csrf'] = csrf_token(session.get(form_url).text)
        headers['X-CSRF-Token'] = ctx['csrf']
        answer = session.post_json(APPLY_ORIGIN + GRAPHQL_PATH, body, headers)
    if answer.status != 200:
        raise RuntimeError(op + ': HTTP ' + str(answer.status))
    parsed = parse_answer(answer.text, op)
    if parsed.get('errors'):
        raise RuntimeError(op + ': GraphQL errors: ' + graphql_errors_text(parsed['errors']))
    data = parsed.get('data')
    if not isinstance(data, dict):
        raise RuntimeError(op + ': the answer carries no data')
    return data


def read_answers(session, ctx, form_url, allowed_ops, log):
    """The App as SHOW_APP returns it: its status fields and questions."""
    data = graphql(session, ctx, 'SHOW_APP', show_app_query(readable_keys(ctx['formKeys'])),
                   {'appUuid': ctx['appUuid']}, allowed_ops, form_url, log)
    app = data.get('app')
    if not isinstance(app, dict):
        raise RuntimeError('SHOW_APP: YC returned no application for the form page\'s app_uuid')
    return app


def write_answers(session, ctx, patch, form_url, allowed_ops, log):
    """One UPDATE_APP carrying the patch; YC's updateApp answer."""
    data = graphql(session, ctx, 'UPDATE_APP', update_app_mutation(readable_keys(ctx['formKeys'])),
                   {'uuid': ctx['appUuid'], 'input': update_input(patch, ctx['updateKind'])},
                   allowed_ops, form_url, log)
    result = data.get('updateApp')
    if not isinstance(result, dict):
        raise RuntimeError('UPDATE_APP: the answer carries no updateApp')
    return result
