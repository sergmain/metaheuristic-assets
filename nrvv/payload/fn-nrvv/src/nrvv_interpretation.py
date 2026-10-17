"""The NEED interpretation of an NRVV project: one session reads its NEEDs as a set and states atomic ASSUMPTION,
READING and OPEN_CHOICE items, each citing the NEEDs it rests on and quoting their words.

The session's input is read-interpretation-input's `interpretationInput`: the stakeholder, the sections of the
expectation, the agreed NEEDs (reqId, revision, clause kind, title, statement, section) and the sessions (id, global,
needs, governable). A later session also sees the first session's checked items, read-only.

The check refuses an answer by writing {"refused": "<rule>"} - the run goes on, and the refused part is repaired later;
it never fails its Task for a rule. Pure apart from run_prompt / run_check.
"""

import json

import mh_task_io as io
import nrvv_assessment as na
import nrvv_cc_answer as ca
import nrvv_cv_need as cv
import nrvv_evidence as ev

KINDS = ('ASSUMPTION', 'READING', 'OPEN_CHOICE')
QUALIFIER_KINDS = ('ENVIRONMENT_FACT', 'SCOPE_LIMITER', 'COST_OBJECTIVE')
FIELDS = ('key', 'kind', 'needs', 'governs', 'title', 'statement', 'rationale', 'evidence')

ANSWER_SHAPE = ('{"items": [{"key": "<session>-<n>", "kind": "ASSUMPTION|READING|OPEN_CHOICE", "needs": ["<NEED reqId>"], '
                '"governs": ["<NEED reqId>"] or ["*"] or [], "title": "...", "statement": "...", "rationale": "...", '
                '"evidence": [{"source": "<NEED reqId>", "quote": "<words of that NEED>"}]}]}')


def context_of(raw):
    """The interpretation input, or a ValueError."""
    try:
        context = json.loads(raw or '')
    except ValueError as e:
        raise ValueError('the interpretation input is not JSON: ' + str(e))
    if not isinstance(context, dict) or not isinstance(context.get('needs'), list) or not isinstance(context.get('sessions'), list):
        raise ValueError('the interpretation input is not {"needs": [...], "sessions": [...]}')
    return context


def session_of(context, session_id):
    """The session `session_id` of the input, or a ValueError."""
    sid = (session_id or '').strip()
    for s in context['sessions']:
        if isinstance(s, dict) and s.get('id') == sid:
            return s
    raise ValueError("the interpretation input has no session '" + sid + "'")


def needs_by_id(context):
    return {str(n['reqId']): n for n in context['needs'] if isinstance(n, dict) and n.get('reqId')}


def is_qualifier(need):
    return str(need.get('kind') or '') in QUALIFIER_KINDS


def qualifiers_of(context, session):
    """The session's qualifier NEEDs (ENVIRONMENT_FACT, SCOPE_LIMITER, COST_OBJECTIVE) - every one must be cited."""
    by_id = needs_by_id(context)
    return [n for n in session.get('needs') or [] if n in by_id and is_qualifier(by_id[n])]


def compose(context, session_id, first_items=None):
    """The prompt of session `session_id`. The answer instruction is the LAST part."""
    session = session_of(context, session_id)
    by_id = needs_by_id(context)
    sid = session['id']
    governable = session.get('governable') or []
    lines = [
        'You read the NEEDs of a project as a set, before any requirement is written. A NEED states what a stakeholder',
        'needs, in the stakeholder\'s words. Some NEEDs are obligations; others qualify them - facts about the world the',
        'system lives in, what matters and what does not, costs to weigh. Read every obligation together with the NEEDs',
        'that qualify it, and state the reading as atomic interpretation items.',
        '',
        'Three kinds of item, and only these:',
        '- ASSUMPTION: a fact about the world outside the system that the NEEDs state, written in the world\'s voice -',
        '  "Sends can arrive at a station out of order." Never a "shall". It holds for the whole system: governs is [].',
        '- READING: how an obligation is read together with the NEEDs that qualify it - "Publishing an update is met when',
        '  the station ends up holding the latest desired price; a price superseded before delivery need not be',
        '  delivered." governs names the obligation NEEDs it governs.',
        '- OPEN_CHOICE: a dimension the NEEDs leave open - "How soon a station holds the latest price is not stated;',
        '  requirements hold for every delay." Never a "shall". governs names the NEEDs whose requirements it leaves',
        '  open.',
        '',
        'Rules:',
        '- Every NEED of kind ENVIRONMENT_FACT, SCOPE_LIMITER or COST_OBJECTIVE listed below is cited (in "needs") by at',
        '  least one item. "needs" names only NEEDs listed below.',
        '- Every item quotes, under "evidence", the words of a NEED it cites that it rests on: at least two words, copied',
        '  exactly as the NEED states them, without double quotes inside. "source" is that NEED\'s reqId.',
        '- A statement holding each, every, all, any, always or never needs a quote holding one of those words; state no',
        '  wider scope than the NEEDs state.',
        '- No item names a programming language, a framework or a test tool.',
        '- A cost the NEEDs want kept low is a cost to measure and report, never a bound: no item turns a COST_OBJECTIVE',
        '  into a prohibition or a limit.',
        '- One meaning per item. Keys are "' + sid + '-1", "' + sid + '-2", ... in order.',
        ('- governs names NEEDs from: ' + ', '.join(governable) + (', or is ["*"] for an item that governs every '
                                                                     'obligation' if session.get('global') else '')
         + '.'),
        '',
    ]
    lines += cv.KIND_HINT + ['']
    sections = context.get('sections') or []
    shown = sorted({by_id[n].get('section') for n in session.get('needs') or []
                    if n in by_id and isinstance(by_id[n].get('section'), int)})
    if shown:
        lines.append('The expectation the NEEDs were taken from' + (' (the sections they come from)' if len(sections) > 1 else '') + ':')
        for i in shown:
            if 0 <= i < len(sections):
                lines.append('')
                for text_line in str(sections[i].get('text') or '').strip().splitlines():
                    lines.append('  ' + text_line)
        lines.append('')
    lines.append('The NEEDs of this session:')
    for n in session.get('needs') or []:
        need = by_id.get(n)
        if need is None:
            continue
        lines.append('')
        lines.append('NEED ' + n + ' (revision ' + str(need.get('revision')) + ', '
                     + (str(need.get('kind')) if need.get('kind') else 'OBLIGATION') + '): ' + str(need.get('title') or '').strip())
        for text_line in str(need.get('statement') or '').strip().splitlines():
            lines.append('  ' + text_line)
    if first_items:
        lines.append('')
        lines.append('Items an earlier session already stated - read-only; do not repeat them, do not contradict them:')
        for it in first_items:
            lines.append('- ' + str(it.get('kind')) + ' citing ' + ', '.join(it.get('needs') or []) + ': '
                         + str(it.get('statement') or '').strip())
    return '\n'.join(lines + [
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object and nothing else:',
        ANSWER_SHAPE,
        cv.ANSWER_TAIL.replace('the findings', 'the items'),
    ])


def _strings(value):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        return None
    out = []
    for x in value:
        if x.strip() not in out:
            out.append(x.strip())
    return out


def items_of(cc_result, context, session_id):
    """CC's items as the canonical answer {"items": [...]}, or a ValueError naming the first rule they break."""
    session = session_of(context, session_id)
    sid = session['id']
    by_id = needs_by_id(context)
    in_session = set(session.get('needs') or [])
    governable = set(session.get('governable') or [])
    text = (cc_result or '').strip()
    fenced = na.FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    data = ca.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get('items'), list) or set(data) != {'items'}:
        raise ValueError('the answer is not {"items": [...]}')
    keys = []
    cited = set()
    out = []
    for i, it in enumerate(data['items']):
        if not isinstance(it, dict):
            raise ValueError('item ' + str(i + 1) + ' is not an object')
        unknown = sorted(set(it) - set(FIELDS))
        if unknown:
            raise ValueError('item ' + str(i + 1) + ' has unknown field(s) ' + str(unknown))
        key = str(it.get('key') or '').strip()
        if not key.startswith(sid + '-') or key in keys:
            raise ValueError("item key '" + key + "' is a duplicate or lacks the prefix '" + sid + "-'")
        keys.append(key)
        kind = str(it.get('kind') or '').strip()
        if kind not in KINDS:
            raise ValueError(key + ': unknown kind ' + repr(kind) + ' - one of ' + ', '.join(KINDS))
        needs = _strings(it.get('needs'))
        if not needs or not set(needs) <= in_session:
            raise ValueError(key + ': needs ' + str(it.get('needs')) + ' are empty or outside the session')
        governs = _strings(it.get('governs'))
        if governs is None:
            raise ValueError(key + ': governs is not a list of reqIds')
        if kind == 'ASSUMPTION' and governs:
            raise ValueError(key + ': an ASSUMPTION holds for the whole system and governs nothing')
        if kind != 'ASSUMPTION' and not governs:
            raise ValueError(key + ': a ' + kind + ' names the NEEDs it governs')
        for g in governs:
            if g == '*':
                if not session.get('global') or len(governs) > 1:
                    raise ValueError(key + ': governs * is the global session\'s alone, and the only entry')
            elif g not in governable:
                raise ValueError(key + ': governs ' + g + ', which this session may not govern')
        statement = str(it.get('statement') or '').strip()
        title = str(it.get('title') or '').strip()
        if not statement or not title:
            raise ValueError(key + ': a blank title or statement')
        rationale = str(it.get('rationale') or '').strip()
        evidence = []
        for e in it.get('evidence') or []:
            if not isinstance(e, dict):
                raise ValueError(key + ': an evidence entry is not an object')
            evidence.append((str(e.get('source') or '').strip(), str(e.get('quote') or '').strip()))
        sources = {n: str(by_id[n].get('statement') or '') for n in needs if n in by_id}
        refusal = ev.interpretation_refusal(key, kind, statement, rationale, evidence, sources)
        if refusal:
            raise ValueError(refusal)
        cited.update(needs)
        out.append({'key': key, 'kind': kind, 'needs': needs, 'governs': governs, 'title': title, 'statement': statement,
                    'rationale': rationale, 'evidence': [{'source': s, 'quote': q} for s, q in evidence]})
    missing = [n for n in qualifiers_of(context, session) if n not in cited]
    if missing:
        raise ValueError('the qualifier NEED(s) ' + ', '.join(missing) + ' are cited by no item')
    return {'items': out}


def checked(cc_result, context, session_id):
    """The checked answer - the items, or {"refused": "<rule>"} when CC's answer breaks a rule (decision 14). An unknown
    session is a defect of the flow, not of the answer: its ValueError fails the Task."""
    session_of(context, session_id)
    try:
        return items_of(cc_result, context, session_id)
    except ValueError as e:
        return {'refused': str(e)}


def _first_items(task):
    metas = task.get('metas') or []
    if io.meta_value(metas, 'variable-for-first-answer') is None:
        return None
    raw = io.read_role(task, 'first-answer')
    if not raw:
        return None
    try:
        answer = json.loads(raw)
    except ValueError:
        return None
    return answer.get('items') if isinstance(answer, dict) else None


def run_prompt(task, function_code):
    context = context_of(io.read_role(task, 'interpretation-input'))
    session_id = (io.read_role(task, 'session') or '').strip()
    prompt = compose(context, session_id, _first_items(task))
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(function_code + ': session ' + session_id + ', ' + str(len(session_of(context, session_id).get('needs') or []))
          + ' NEED(s), ' + str(len(prompt)) + ' chars')


def run_check(task, function_code):
    context = context_of(io.read_role(task, 'interpretation-input'))
    session_id = (io.read_role(task, 'session') or '').strip()
    answer = checked(io.read_role(task, 'cc-result'), context, session_id)
    io.write_text(io.output_role(task, 'interpretation'), json.dumps(answer, ensure_ascii=False))
    if 'refused' in answer:
        print(function_code + ': session ' + session_id + ' REFUSED: ' + ca.excerpt(answer['refused']))
    else:
        print(function_code + ': session ' + session_id + ', ' + str(len(answer['items'])) + ' item(s): '
              + ', '.join(i['key'] + '/' + i['kind'] for i in answer['items']))
