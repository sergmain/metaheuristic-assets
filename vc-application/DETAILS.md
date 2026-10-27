# vc-application - DETAILS

Applying to venture funds from MH: the fund's application form surveyed, then filled from Variables. YC is the
first fund; every fund-specific part is one adapter, one Function descriptor and one wrapper `.mhsc`.

| DAHF flow | what it is for, in business terms | `.mhsc` | state |
|---|---|---|---|
| VC form survey | know every input field of a fund's application form, and the inputs an apply flow for that fund declares | `vc-form-survey-yc-synthetic-1.0` (YC), over `vc-form-survey.mhscp` - section A | `synthetic` experiment |
| VC apply | fill and save a fund's application from the run's input Variables | none yet - its inputs are defined by the survey (section A, part 3 "The YC apply inputs") | not started |

Payload `vc-application/payload/fn-vc-form-survey` (shared by every fund) · Function per fund:
`mh.asset.vc-form-survey-yc_1.0` (`functions/fn-vc-form-survey-yc`, Vault entry `VC_YC_AUTH`).

**Adding a fund** - nothing in the shared graph or the core changes:

1. `payload/fn-vc-form-survey/src/vc_fund_<fund>.py` - `FUND`, `may_send(method, url)`, `survey(session, login,
   password, form_url, log)` returning `{host, path, component, version, props}`, and optionally its own
   `extract_fields(props)`; registered in `vc_form_survey.ADAPTERS`; unit tests in `tests/test_vc_fund_<fund>.py`.
2. `functions/fn-vc-form-survey-<fund>/mh-function.yaml` - code `mh.asset.vc-form-survey-<fund>_1.0`, the same
   payload, `api.keyCode` = the fund's Vault entry (a descriptor carries exactly one key).
3. `source-codes/vc-form-survey-<fund>-synthetic-1.0.mhsc` - `def fund`, `def survey_fn`, `include "vc-form-survey"`.

---

## A. VC form survey - `vc-form-survey-yc-synthetic-1.0`

### 1. Purpose

Sign in to a fund's application site with the founder's account and read the application form: every input field
it defines - key, label, type, whether it is required, its choices and limits - and, from that, the `variables { }`
block an apply flow for the fund declares, one input per field. It is the synthetic-mode step that defines the apply
flow; it never writes to the fund's site.

**Business frame (DAHF §H.5), derived from the request - no question was needed:**

- **Objective:** the YC application at the url the human gave can be filled from MH - for this task, in synthetic
  mode: every input field of the form is known, and the global input Variables of the apply flow are defined from it.
  Further funds follow the same path.
- **Success:** a synthetic ExecContext reaches FINISHED having signed in with `VC_YC_AUTH`; `formFields` lists every
  input field the form defines (F2), and `applyVariables` declares exactly one input per listed field (F5).
- **Invariants:** nothing is written to the application (F3); the credential appears nowhere (F4); no applicant
  content is copied into a Variable (F6); synthetic mode end to end - nothing durable is written anywhere; MH and RG
  untouched; extensible - nothing YC-specific in the shared graph or the generic core.
- **Done:** the field list and the defined apply inputs, read back by value from the run's Variables, beside the
  ExecContext id.

### 2. The graph

One process, `survey` -> `${survey_fn}` (`mh.asset.vc-form-survey-yc_1.0` for YC), `tries 1`, `timeout 180`. The
order that matters is inside the Function:

1. **The secret handoff comes first** - the Processor's `accept()` waits 10 seconds.
2. **Everything resolvable is resolved before the fund's site is called** - the adapter, the inputs, both output
   declarations, the shape of the credential.
3. **The adapter signs in when the site asks for it, then reads the form page.** For YC: `GET` the form url (YC
   redirects to its SSO), `POST /start_sign_in`, `POST /sign_in`, `GET` the redirect, `GET` the form - see
   `vc_fund_yc.py` for the protocol as YC's own client speaks it.
4. **Fields are extracted from the page's props** - the adapter's `extract_fields` when it has one, else the generic
   one: a dict with a label and an identity is a field, a dict with fields beneath it is a section, a dict inside
   `options` / `choices` is a choice.
5. **Both outputs are written**, and every field is printed as `variable <- key (type, required)`.

`tries 1`: a sign-in that failed is not repeated; another attempt only moves the site toward a captcha.

### 3. The run-data contract

| variable | dir | meaning | permitted values |
|---|---|---|---|
| `formUrl` | in | the application's page | for YC an https url on `apply.ycombinator.com`, e.g. `https://apply.ycombinator.com/apps/<id>/edit` |
| `production` | in, nullable | read and reported only; a survey writes nothing durable in either mode | JSON `null` at launch |
| `formFields` | out | the inventory, JSON: `fund`, `form` {host, path, component, version}, `fieldCount`, `fields` [{key, label, type, required, options, limits, help, section, path, variable}], `propsSkeleton` | - |
| `applyVariables` | out | the apply flow's `variables { }` block: one `<- <variable>` per field, `?` unless the form marks the field required, the label as a comment above it | - |

- **Credential:** Vault entry `VC_YC_AUTH`, the plain `login:password` of the founder's YC account (an e-mail or a YC
  username, a colon, the password - which may contain colons). Declared as `api.keyCode` of the YC descriptor and
  handed over on the loopback secret channel; never a Variable.
- **Company:** launch where the Vault holding `VC_YC_AUTH` - or the management company's (uniqueId 1), whose keys have
  priority - is UNLOCKED. Imports land in company 2.
- **Launch:** `mh_create_exec_context_with_variables`, `production` passed as JSON `null`.
- ⚠️ **What needs a person:** YC may answer a sign-in with a reCAPTCHA, a two-factor code or an e-mailed new-device
  code. Each ends the run with `SignInNeedsPerson` naming which one.

### 4. Durable side effects

None in MH: no meta storage, no project; the run leaves its two output Variables. On YC: a signed-in session (YC may
e-mail the account about a new sign-in). Nothing in the application changes.

### 5. Fitness criteria

| # | criterion | hardness | type | how it is observed |
|---|---|---|---|---|
| F1 | the sign-in completes without a person: the run reads the form page on `apply.ycombinator.com`, not YC's `SignIn` page | hard | D | the Task console (`form page: <component> at apply.ycombinator.com/...`) and `formFields.form` |
| F2 | `formFields` lists every input field of the form, each once, each with a key and a label | hard | D | `formFields.fields` read in full, against the field definitions visible in `formFields.propsSkeleton` - every definition there is in `fields`, and nothing in `fields` is a section or a choice |
| F3 | nothing is written to the application: every request is a GET, except POSTs to `account.ycombinator.com` `/start_sign_in` and `/sign_in` | hard | D | the Task console - one line per request and per redirect; and in code, `vc_fund_yc.may_send` asked by the session before every request and redirect (`test_may_send_never_writes_to_the_application`, `test_refused_request_never_reaches_the_server`) |
| F4 | the credential appears in no console line and no Variable | hard | D | in code: the password is passed only into the `/sign_in` body; no `print` takes it; `split_credential` messages never carry the value (tests); the console prints paths without queries |
| F5 | `applyVariables` declares exactly one input per field of `formFields`, names unique, `?` exactly where `required` is not `true` | hard | D | `applyVariables` read in full against `formFields.fields[].variable` / `.required` |
| F6 | no applicant content is copied into a Variable | soft | D | `formFields` read in full: `fields` carries definitions only; `propsSkeleton` shows other strings as `str:<length>` (tests: `test_skeleton_*`) |

### 6. Corrections

None yet.

### 7. Experiments

| id | hypothesis | answers | SourceCode | riskiest assumption | verdict |
|---|---|---|---|---|---|
| E1 | the request taken literally: sign in to YC over plain HTTP the way YC's own SSO client does, read the form page's Inertia props, extract the fields generically, emit the apply inputs | - | `vc-form-survey-yc-synthetic-1.0` | YC lets a plain HTTP client sign in with the password alone - no reCAPTCHA, no two-factor code, no e-mailed new-device code; the cheapest run that shows it is this run | OPEN |
| E2 | if the field definitions are not in the props: read them from the edit page's JavaScript chunk (the client-side form definition) | E1's riskiest alternative: the props carry answers but not definitions | - | the edit component's chunk names the fields statically | OPEN |
| E3 | if YC demands a captcha for a plain HTTP client: a real browser (Edge, installed on the Processor's box) driven over its debugging protocol | E1's riskiest assumption | - | the captcha is not demanded of a real browser; an e-mailed code would still need a person | OPEN |

Measured alike: no numeric metric; F1-F6 are pass/fail.

### 8. Production readiness

`vc-form-survey-yc-synthetic-1.0` carries `synthetic` in its name: never production ready (§0.21). The survey reads
only; a production apply flow that wants it as a pre-flight check (has the form changed?) gets its own candidate.
