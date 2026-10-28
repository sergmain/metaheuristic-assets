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
   password, form_url, log)` returning `{host, path, html}` of the signed-in form page, and optionally its own
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
3. **The adapter signs in when the site asks for it, then fetches the form page.** For YC: `GET` the form url (YC
   redirects to its SSO), `POST /start_sign_in`, `POST /sign_in`, `GET` the redirect, `GET` the form - see
   `vc_fund_yc.py` for the protocol as YC's own client speaks it.
4. **The page is read by the core (`vc_page.py`), whatever carries the form:** the state a JS framework embeds
   (Inertia attribute or script, react-rails, react_on_rails, Next.js, `window.REACT_COMPONENTS.push(...)` - YC's apply
   site - any JSON script) and the server-rendered form controls. Fields come from the embedded state when it
   defines any - the adapter's `extract_fields` first (YC: one field per entry of the AppForm's `active_question_groups`,
   its group as the section), else the generic one: a
   dict with a label and an identity is a field, a dict with fields beneath it is a section, a dict inside `options` /
   `choices` is a choice - else from the form controls, else none. The page's structure (names, counts and
   string-blanked script sketches only) is recorded either way.
5. **Both outputs are written**, and every field is printed as `variable <- key (type, required)`. No field found
   is not a failure of the Task: the outputs carry the page's structure for the next experiment.

`tries 1`: a sign-in that failed is not repeated; another attempt only moves the site toward a captcha.

### 3. The run-data contract

| variable | dir | meaning | permitted values |
|---|---|---|---|
| `formUrl` | in | the application's page | for YC an https url on `apply.ycombinator.com`, e.g. `https://apply.ycombinator.com/apps/<id>/edit` |
| `production` | in, nullable | read and reported only; a survey writes nothing durable in either mode | JSON `null` at launch |
| `formFields` | out | the inventory, JSON: `fund`, `form` {host, path, embedding, component, version}, `source` (`props`, `html-form` or `none`), `fieldCount`, `candidates` (fields found per source), `fields` [{key, label, type, required, options, limits, help, section, path, variable}], `propsSkeleton` (or null), `pageStructure` | - |
| `applyVariables` | out | the apply flow's `variables { }` block: one `<- <variable>` per field, `?` unless the form marks the field required, the label as a comment above it | - |

- **Credential:** Vault entry `VC_YC_AUTH`, the plain `login:password` of the founder's YC account (an e-mail or a YC
  username, a colon, the password - which may contain colons). Declared as `api.keyCode` of the YC descriptor and
  handed over on the loopback secret channel; never a Variable.
- **Company:** launch where the Vault holding `VC_YC_AUTH` - or the management company's (uniqueId 1), whose keys have
  priority - is UNLOCKED. Imports land in company 2.
- **Launch:** `mh_create_exec_context_with_variables`, `production` passed as JSON `null`.
- ⚠️ **What needs a person:** YC may answer a sign-in with a reCAPTCHA, a two-factor code or an e-mailed new-device
  code. Each ends the run with `SignInNeedsPerson` naming which one.

#### The YC apply inputs

Defined by E5 (ExecContext #5406, `applyVariables`): the global input Variables of a YC apply flow, one per question of
the application at 2026-10-27, `yc` + the field name in PascalCase. Required (no `?`): `ycVideoS3Key`, `ycName`,
`ycDescribe`, `ycFutureBatchName`; every other input is nullable.

| group | inputs |
|---|---|
| Founders | `ycFounderBios?` (no label: the founders' own profiles, a form of their own), `ycMeet?`, `ycOthers2?`, `ycCofounder?` |
| Founder Video | `ycVideo?`, `ycVideoS3Key` (an upload) |
| Company | `ycName`, `ycDescribe`, `ycUrl?`, `ycDemo?`, `ycDemoS3Key?` (an upload), `ycProductLink?`, `ycProductCreds?`, `ycMake?`, `ycWhere?`, `ycWherewhy?` |
| Progress | `ycHowfar?`, `ycWorked?`, `ycTechstack?`, `ycCodingAgentSession?` (an upload), `ycStage?`, `ycUsernums?`, `ycWhenbeta?`, `ycRevenue?`, `ycRevenueamount?`, `ycRevenuesource?`, `ycGrowthrate?`, `ycSince?`, `ycAcc?` |
| Idea | `ycExp?`, `ycGet?`, `ycMoney?`, `ycIdeas?` |
| Equity | `ycIncyet?`, `ycInctype?`, `ycIncpercent?`, `ycPercent2?`, `ycInvestyet?`, `ycIncinvest?`, `ycInvestamount?`, `ycBank?`, `ycBurn?`, `ycRunway?`, `ycCurrentlyraising?`, `ycRaisingdetails?` |
| Curious | `ycWhyapply?`, `ycHowhear?`, `ycReferralCode?` |
| Batch Preference | `ycBatchPreference?`, `ycFutureBatchName`, `ycFutureBatchWhy?` |

- ⚠️ `ycFutureBatchName` is required on the page but asked only when a future batch is chosen: an apply flow for the
  upcoming batch declares it `?` - the page's flag is per question, not per path through the form (E6).
- ⚠️ Types and choices are not known yet (E6): which inputs are a choice (`ycHowfar`, `ycIncyet`, `ycBatchPreference`,
  ...) and what values they accept is in the bundle's code.
- `production` (nullable) joins these in the apply flow's own `.mhsc`, as in every `.mhsc`.

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

- **2026-10-27, E1, ExecContext #5156, Task #326554 (ERROR, exit 1, payload `362f738`).** Console, one line per
  request: `GET apply.../edit` -> 302 -> `account.ycombinator.com/` 200 (`SignIn`), `POST /start_sign_in` 200,
  `POST /sign_in` 200 (`signed in`), `GET apply.../edit` 200 - then `the page carries no Inertia data-page attribute`.
  The sign-in - E1's riskiest assumption - held: no reCAPTCHA, no two-factor code, no e-mailed code; the only POSTs
  were the two sign-in calls (F3). What failed is the assumption that the apply site embeds its page the way the SSO
  does. Learned: the form page is read without assuming its framework (`vc_page.py`), and its structure is recorded
  whenever no field is found. The full console is in `mh_task.function_exec_results` - the MCP excerpt stops after
  the first request.
- **2026-10-27, while writing E2's tests.** A `<textarea>` inside a `<label>` made the typed text part of the label -
  applicant content into `formFields` (F6). `test_html_fields_never_carry_what_was_typed` now covers it, and the
  parser skips textarea content.
- **2026-10-27, E2, ExecContext #5286, Task #339656 (OK, payload `aa1946b`).** `formFields` (Variable #249980, read in
  full): signed in, form page `apply.ycombinator.com/apps/.../edit` of 46,035 bytes; `source` none, 0 fields; no
  embedded framework state, 0 forms, 0 controls; 9 inline scripts; 4 hash-like element ids; scripts
  `bookface-static.ycombinator.com/vite/assets/apply-NOt1hKGv.js`, `apply_chat_tailwind-*.js`, Google Maps. Learned,
  from the public bundle read from outside: it mounts every entry of `window.REACT_COMPONENTS` ({divId, component,
  props}) - the hash ids are the divIds, the inline scripts the pushes; the application form shows a question only
  when the server's `questionLabels` prop has a label for it; answers are `app.questions[fieldName]`; types and
  validation are in the bundle's code. A Task that ends OK keeps no console in `mh_task.function_exec_results` - the
  output Variables are the evidence. The Desktop `metaheuristic` connection was down for this run: it was launched
  and read over the Dispatcher's own MCP endpoint `/rest/v1/mcp`, called from the box (MH's REST has no route that
  initializes an ExecContext's source-level inputs).
- **2026-10-27, E3, ExecContext #5295, Task OK (payload `dbdbe1c`).** `formFields` (Variable #250389, 2,571 bytes, read
  in full - the MCP read's default budget truncates at 1,024 bytes, so it was re-read with `maxBytes`): 0 fields,
  `embedding` null. `inlineScriptSketches` showed why: three `window.REACT_COMPONENTS.push({ divId: "~", component: "~",
  props: {...} })` scripts (435, 8,372 and 180 bytes) - the wrapper's keys are bare, so it is not JSON, and only its
  `props` value is. Learned: read the wrapper as JS and its props as JSON (`vc_page.react_component_pushes`).
- **2026-10-27, E4, ExecContext #5319, both Tasks OK (payload `1b9b0c1`).** Launched from this chat as "E2" while the
  E3/E4 work above was pushed from another one, so it ran E4's payload; launched and read over HTTP from the box -
  `/rest/v1/mcp` for the launch, `GET /rest/v1/dispatcher/source-code/exec-context/{ec}/download-variable/{id}` for
  the outputs (Variable content of this home is on disk: psql `lo_get` returns nothing). `formFields` (Variable
  #251437, 17,823 bytes, read in full): `embedding` `react-components` - `components/Header`, `components/AppForm`,
  `components/Footer` - and 0 fields; `applyVariables` (#251438) an empty block. The AppForm props carry no
  `questionLabels`: they are `active_question_groups`, `app_uuid`, `future_batch_names`, `update_kind`, `user_hnid`,
  and `active_question_groups` is `{group: {fieldName: {prompt: {q, required, subtitle?, placeholder?} | null}}}` -
  51 entries in 8 groups (Founders 4, Founder Video 2, Company 10, Progress 13, Idea 4, Equity 12, Curious 3, Batch
  Preference 3); 50 prompts carry `q` and `required`, 8 a `subtitle`, 3 a `placeholder`; `founderBios`' prompt is
  null. `apply-*.js` (`AppForm` = `({user_hnid, active_question_groups, update_kind, app_uuid, future_batch_names})`)
  builds its labels from `prompt.q`; answers arrive later over GraphQL (`/graphql`). Learned: the question
  definitions ARE in the server's props, under the snake-case name - CT `test_yc_active_question_groups.py` (Green-1
  `[]`, Red, Green-3), tests 96/96.
- **2026-10-27, E5, ExecContext #5406, both Tasks OK (payload `c54075e`).** `formFields` (Variable #258293, 38,550 bytes)
  and `applyVariables` (#258294, 104 lines) read in full. `source` `props`, `fieldCount` 51, `candidates` {props 51,
  html-form 0}. Checked against the page independently of the extraction: the 51 (group, fieldName) entries of
  `propsSkeleton...active_question_groups` equal the fields' (section, key), same order, keys unique (F2); 51 `<-`
  lines, names unique and in field order, `?` exactly where `required` is not `true` (F5); `app_uuid` and `user_hnid`
  stay `str:<length>` (F6). Seven labels differ from the skeleton's `q` only because the skeleton cuts at 160
  characters - each is a prefix match; `percent2`'s label is cut at the 300-character label cap. Two limits of the
  definition, both in the bundle's code rather than the props (E6): no field has a type - three are uploads
  (`videoS3Key`, `demoS3Key`, `codingAgentSession`); and `required` is per question, not per path through the form -
  `futureBatchName` is required on the page but asked only when a future batch is chosen.

### 7. Experiments

| id | hypothesis | answers | SourceCode | riskiest assumption | verdict |
|---|---|---|---|---|---|
| E1 | the request taken literally: sign in to YC over plain HTTP the way YC's own SSO client does, read the form page's Inertia props, extract the fields generically, emit the apply inputs | - | `vc-form-survey-yc-synthetic-1.0` (payload `362f738`) | YC lets a plain HTTP client sign in with the password alone - no reCAPTCHA, no two-factor code, no e-mailed new-device code; the cheapest run that shows it is this run | REJECTED - ExecContext #5156: the sign-in held (F1's sign-in half, F3), but the signed-in form page has no Inertia `data-page` |
| E2 | read the form page whatever carries it: every standard embedded state, then the server-rendered form controls; record the page's structure when neither yields a field | E1, ExecContext #5156: the apply page is not Inertia | `vc-form-survey-yc-synthetic-1.0` (payload `aa1946b`) | the form's definition reaches the server's HTML at all - in an embedded state or as form controls - rather than being fetched by the page's JavaScript after load | REJECTED - ExecContext #5286: Task OK, 0 fields; no standard embedding, 0 forms, 0 controls; 9 inline scripts and the bundle `apply-NOt1hKGv.js` |
| E3 | the edit page's inline scripts push `{divId, component, props}` onto `window.REACT_COMPONENTS`, and the props carry `questionLabels` - the set of questions the form shows (`hideQuestionsWithoutLabels`), fieldName -> {q, subtitle, placeholder}; the YC adapter reads the fields from it | E2, ExecContext #5286, and the public bundle `apply-NOt1hKGv.js` read from outside | `vc-form-survey-yc-synthetic-1.0` (payload `dbdbe1c`) | the inline scripts pass the props as JSON (a literal or `JSON.parse` of a string) - the sketches in `pageStructure.inlineScriptSketches` show the shape if not | REJECTED - ExecContext #5295: the pushes are there (3), but the wrapper is a JS literal with bare keys - `push({ divId: "~", component: "~", props: {JSON} })` - so nothing was read; 0 fields |
| E4 | E3 with the wrapper read as JS: `component` from its string literal, `props` from the balanced JSON object after `props:` | E3, ExecContext #5295: `inlineScriptSketches` | `vc-form-survey-yc-synthetic-1.0` (payload `1b9b0c1`) | the props of the 8,372-byte push carry `questionLabels` | REJECTED - ExecContext #5319: the three pushes are read (`react-components`), but no prop is named `questionLabels`; the definitions are under the AppForm's `active_question_groups`; 0 fields |
| E5 | one field per entry of the AppForm's `active_question_groups`: key = the field name, label = `prompt.q`, required = `prompt.required`, help = `subtitle` or `placeholder`, section = the group | E4, ExecContext #5319: `propsSkeleton` | `vc-form-survey-yc-synthetic-1.0` (payload `c54075e`) | the 51 entries are the whole form - no question is added by the bundle without a server entry | CHAMPION - ExecContext #5406: 51 fields from `props`, the page's 51 entries in the same order (F2), 51 inputs, `?` exactly where `required` is not true (F5), F1/F6 hold; types unknown - E6 |
| E6 | if the field set is right but types, required flags and choices are needed: read them from the bundle's code - each field component is called with a `fieldName` literal (125 in `apply-*.js`) and its options / validation schema | E3/E4, once the set holds: `questionLabels` carries no types | - | the bundle's minified calls keep `fieldName` and `options` as literals next to the component they render | OPEN |
| E7 | if YC demands a captcha for a plain HTTP client: a real browser (Edge, installed on the Processor's box) driven over its debugging protocol | E1's riskiest assumption - not observed in E1-E4 | - | the captcha is not demanded of a real browser; an e-mailed code would still need a person | OPEN |

Measured alike: no numeric metric; F1-F6 are pass/fail.

### 8. Production readiness

`vc-form-survey-yc-synthetic-1.0` carries `synthetic` in its name: never production ready (§0.21). The survey reads
only; a production apply flow that wants it as a pre-flight check (has the form changed?) gets its own candidate.
