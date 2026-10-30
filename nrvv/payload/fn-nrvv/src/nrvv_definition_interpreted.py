"""The definition of a requirement set under the NEED interpretation, by parts:

- TOP-LEVEL, one session per derivation NEED (the subject): the requirements that restate it, read through the
  interpretation items governing it, each quoting the NEED words it rests on;
- BOUNDARY, one session: the Interface and the Environment over every top-level requirement, the Environment simulating
  every ASSUMPTION item;
- DESIGN, one session per top-level requirement: how it is met.

The inputs are read-definition-input's definitionInput / boundaryInput / designInput. A check refuses an answer by
writing {"refused": "<rule>"} - the run goes on, and the refused part is repaired later; it never fails its Task for a
rule. Pure apart from the run_* functions.
"""

import json

import mh_task_io as io
import nrvv_assessment as na
import nrvv_cc_answer as ca
import nrvv_cv_need as cv
import nrvv_evidence as ev

ASKED_MAX_TITLE_CHARS = 80
# plan 050 decision 4: at most this many requirements of a TOP-LEVEL part cite its subject NEED - one rule with the Java
# re-check's NrvvConsts.TOP_LEVEL_PER_NEED_MAX
TOP_LEVEL_PER_NEED_MAX = 3
TOP_FIELDS = ('key', 'needs', 'readings', 'title', 'statement', 'rationale', 'evidence')
BOUNDARY_FIELDS = ('key', 'parent', 'assumptions', 'title', 'statement', 'rationale', 'evidence')
DESIGN_FIELDS = ('key', 'parent', 'title', 'statement', 'rationale', 'evidence')

V5_RULES = [
    '- One obligation per requirement: one verifiable "The service shall ..." statement.',
    '- Verifiable: an observer can decide from outside whether the system meets it.',
    '- Language-neutral: name no programming language, module, file, class, framework, library or test tool.',
    '- You decide alone - nobody answers questions.',
    '- A statement holds only what the NEEDs state, or what holds under EVERY reading of them.',
    '- Where a NEED is ambiguous, choose no reading: write the statement so that it holds under every reading, and add',
    '  to its rationale one line "ambiguity: <what is ambiguous>" per ambiguity.',
    '- No number, duration, rate or limit the NEEDs do not state appears in a statement.',
    '- A COST_OBJECTIVE NEED is restated as an obligation to measure and report that cost - never as a bound on it.',
    '- A rationale never begins with "assumed:".',
    '- A title of at most ' + str(ASKED_MAX_TITLE_CHARS) + ' characters.',
]

EVIDENCE_RULES = [
    '- Quote, under "evidence", the words each clause rests on: at least two words copied exactly as the NEED (or the',
    '  followed item) states them, without double quotes inside; "source" is that NEED\'s or item\'s reqId.',
    '- A statement holding each, every, all, any, always or never needs a quote holding one of those words.',
    '- A digit in a statement appears in one of its quotes.',
]

# plan 053 P6: a derived item - design, Interface, Environment - quotes what it rests on, as a top-level requirement does:
# its own rationale is the model's account, not evidence of why it wrote it (Chen et al. 2025). The sources are the item's
# parent top-level requirement and the interpretation items the part is given (the parent itself quotes the NEEDs).
DERIVED_EVIDENCE_RULES = [
    '- Quote, under "evidence", the words each item rests on: at least two words copied exactly as its parent top-level',
    '  requirement (or an interpretation item listed below) states them, without double quotes inside; "source" is that',
    '  requirement\'s or item\'s reqId.',
]
DERIVED_EVIDENCE_SHAPE = '"evidence": [{"source": "<reqId>", "quote": "<words>"}]'


def _evidence(e):
    return [(str(x.get('source') or '').strip(), str(x.get('quote') or '').strip())
            for x in e.get('evidence') or [] if isinstance(x, dict)]


def _evidence_out(evidence):
    return [{'source': a, 'quote': b} for a, b in evidence]


def _load(raw, what):
    try:
        data = json.loads(raw or '')
    except ValueError as e:
        raise ValueError('the ' + what + ' is not JSON: ' + str(e))
    if not isinstance(data, dict):
        raise ValueError('the ' + what + ' is not a JSON object')
    return data


def subject_of(definition_input, subject):
    """The entry of `subject` in definitionInput, or a ValueError."""
    for s in definition_input.get('subjects') or []:
        if isinstance(s, dict) and isinstance(s.get('need'), dict) and s['need'].get('reqId') == (subject or '').strip():
            return s
    raise ValueError("the definition input has no subject '" + str(subject) + "'")


def _need_line(n):
    return ('NEED ' + str(n.get('reqId')) + ' (revision ' + str(n.get('revision')) + ', '
            + (str(n.get('kind')) if n.get('kind') else 'OBLIGATION') + '): ' + str(n.get('title') or '').strip()
            + '\n  ' + str(n.get('statement') or '').strip().replace('\n', '\n  '))


def _item_line(i):
    governs = i.get('governs') or []
    return ('- ' + str(i.get('reqId')) + ' ' + str(i.get('kind')) + (' governing ' + ', '.join(governs) if governs else '')
            + ' (citing ' + ', '.join(i.get('needs') or []) + '): ' + str(i.get('statement') or '').strip())


def _answer_object(cc_result):
    text = (cc_result or '').strip()
    fenced = na.FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    data = ca.loads(text)
    if not isinstance(data, dict):
        raise ValueError('CC answered no JSON object')
    return data


def _strings(value, what):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(what + ' is not a list of reqIds')
    out = []
    for x in value:
        if x.strip() not in out:
            out.append(x.strip())
    return out


def _items(data, name, fields):
    raw = data.get(name)
    if not isinstance(raw, list):
        raise ValueError("'" + name + "' is missing or not an array")
    keys = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError('item ' + str(i + 1) + " of '" + name + "' is not an object")
        unknown = sorted(set(entry) - set(fields))
        if unknown:
            raise ValueError('item ' + str(i + 1) + " of '" + name + "' has unknown field(s) " + str(unknown))
        key = str(entry.get('key') or '').strip()
        if not key or key in keys:
            raise ValueError("item key '" + key + "' of '" + name + "' is blank or used twice")
        keys.append(key)
        for field in ('title', 'statement', 'rationale'):
            if not str(entry.get(field) or '').strip():
                raise ValueError(key + ' has no ' + field)
        if len(str(entry.get('title')).strip()) > ASKED_MAX_TITLE_CHARS:
            raise ValueError(key + ': the title is longer than ' + str(ASKED_MAX_TITLE_CHARS) + ' characters')
    return raw


def _refused(fn):
    try:
        return fn()
    except ValueError as e:
        return {'refused': str(e)}


# ==================== TOP-LEVEL ====================

def compose_top(definition_input, subject):
    s = subject_of(definition_input, subject)
    need = s['need']
    lines = [
        'You define the REQUIREMENTS of a NEW software system that restate ONE NEED of its stakeholders - the subject',
        'below. A NEED says, in the stakeholders\' words, what they need. A requirement restates it as an obligation of the',
        'system: what the system shall do - never how. There is no code, and you must not assume any.',
        '',
        'Read the subject THROUGH the interpretation items that govern it: an item states how the NEEDs are read as a set',
        '- what qualifies the subject, what it leaves open. A requirement follows every item that governs its subject and',
        'names each item it follows in "readings"; it may cite, in "needs", the NEEDs those items cite.',
        '',
        'Rules:',
    ] + V5_RULES + EVIDENCE_RULES + [
        '- At least one requirement cites the subject in "needs". Keys ' + str(need.get('reqId')) + '-1, -2, ... in order.',
        '- At most ' + str(TOP_LEVEL_PER_NEED_MAX) + ' requirements cite the subject: restate the NEED, do not elaborate it.',
        '',
    ] + cv.KIND_HINT + ['', 'The subject:', '', _need_line(need), '']
    if s.get('readings'):
        lines.append('The interpretation items governing it:')
        lines += [_item_line(i) for i in s['readings']]
        lines.append('')
    if s.get('needs'):
        lines.append('The NEEDs those items cite:')
        for n in s['needs']:
            lines.append('')
            lines.append(_need_line(n))
        lines.append('')
    return '\n'.join(lines + [
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object and nothing else:',
        '{"requirements": [{"key": "' + str(need.get('reqId')) + '-1", "needs": ["<NEED reqId>"], "readings": ["<item reqId>"],'
        ' "title": "...", "statement": "The service shall ...", "rationale": "...", "evidence": [{"source": "<reqId>",'
        ' "quote": "<words>"}]}]}',
        cv.ANSWER_TAIL.replace('the findings', 'the requirements'),
    ])


def check_top(cc_result, definition_input, subject):
    s = subject_of(definition_input, subject)
    subject_id = s['need']['reqId']
    needs = {subject_id: s['need']}
    for n in s.get('needs') or []:
        needs[n['reqId']] = n
    readings = {i['reqId']: i for i in s.get('readings') or []}

    def checked():
        data = _answer_object(cc_result)
        if set(data) != {'requirements'}:
            raise ValueError('the answer is not {"requirements": [...]}')
        raw = _items(data, 'requirements', TOP_FIELDS)
        if not raw:
            raise ValueError('the answer holds no requirement')
        out = []
        for e in raw:
            key = e['key'].strip()
            cited = _strings(e.get('needs'), key + ': needs')
            followed = _strings(e.get('readings'), key + ': readings')
            if not cited or not set(cited) <= set(needs):
                raise ValueError(key + ': needs ' + str(cited) + ' are empty or outside the subject and its items\' NEEDs')
            if not set(followed) <= set(readings):
                raise ValueError(key + ': readings ' + str(followed) + ' are not items governing the subject')
            evidence = [(str(x.get('source') or '').strip(), str(x.get('quote') or '').strip())
                        for x in e.get('evidence') or [] if isinstance(x, dict)]
            sources = {r: str(needs[r].get('statement') or '') for r in cited}
            sources.update({r: str(readings[r].get('statement') or '') for r in followed})
            kinds = [needs[r].get('kind') for r in cited if ev.is_derivation_subject(needs[r].get('kind'))]
            statement, rationale = e['statement'].strip(), e['rationale'].strip()
            refusal = ev.top_level_refusal(key, statement, rationale, evidence, sources, kinds)
            if refusal:
                raise ValueError(refusal)
            if rationale.lower().startswith('assumed:') or '\nassumed:' in rationale.lower():
                raise ValueError(key + ': a rationale never holds "assumed:" - a requirement that restates NEEDs assumes nothing')
            out.append({'key': key, 'needs': cited, 'readings': followed, 'title': e['title'].strip(), 'statement': statement,
                        'rationale': rationale, 'evidence': [{'source': a, 'quote': b} for a, b in evidence]})
        if not any(subject_id in r['needs'] for r in out):
            raise ValueError('no requirement cites the subject ' + subject_id)
        citing = [r['key'] for r in out if subject_id in r['needs']]
        if len(citing) > TOP_LEVEL_PER_NEED_MAX:
            raise ValueError(str(len(citing)) + ' requirements ' + str(citing) + ' cite the subject: at most '
                             + str(TOP_LEVEL_PER_NEED_MAX) + ' requirements cite the subject ' + subject_id)
        return {'requirements': out}

    return _refused(checked)


# ==================== BOUNDARY ====================

def compose_boundary(boundary_input):
    reqs = boundary_input.get('requirements') or []
    items = boundary_input.get('items') or []
    lines = [
        'You define the BOUNDARY of a NEW software system that meets the top-level requirements below. The system is the',
        'SERVER SIDE: the part that will be implemented. Everything outside it - its clients and the transport between',
        'them and the server side - is not implemented: the tests SIMULATE it, deterministically.',
        '',
        'Answer two lists, every item under exactly ONE top-level requirement, named by its reqId in "parent":',
        '- "interface": the boundary every test and the implementation share - each operation the server side offers',
        '  (its name, parameters and result) and every port through which it sends to, or learns from, what lies outside',
        '  it. Language-neutral. At least one item.',
        '- "environment": what lies outside the server side and how the tests simulate it. The simulation is',
        '  deterministic and simulates ONLY what the ASSUMPTION items state. Every ASSUMPTION item below is named, in',
        '  "assumptions", by at least one environment item. At least one item.',
        '',
        'Rules:',
        '- Language-neutral: name no programming language, module, file, class, framework, library or test tool.',
        '- An OPEN_CHOICE item stays open: no item fixes the dimension it leaves open.',
    ] + DERIVED_EVIDENCE_RULES + [
        '- A title of at most ' + str(ASKED_MAX_TITLE_CHARS) + ' characters. Keys IF-1, IF-2, ... and EN-1, EN-2, ... in order.',
        '',
        'The top-level requirements:',
    ]
    for r in reqs:
        lines.append('')
        lines.append(str(r.get('reqId')) + ' - ' + str(r.get('title') or '').strip())
        lines.append('  ' + str(r.get('statement') or '').strip())
    lines.append('')
    lines.append('The ASSUMPTION and OPEN_CHOICE items:')
    lines += [_item_line(i) for i in items] or ['- none']
    return '\n'.join(lines + [
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object and nothing else:',
        '{"interface": [{"key": "IF-1", "parent": "<reqId>", "title": "...", "statement": "...", "rationale": "...", '
        + DERIVED_EVIDENCE_SHAPE + '}],'
        ' "environment": [{"key": "EN-1", "parent": "<reqId>", "assumptions": ["<ASSUMPTION reqId>"], "title": "...",'
        ' "statement": "...", "rationale": "...", ' + DERIVED_EVIDENCE_SHAPE + '}]}',
        cv.ANSWER_TAIL.replace('the findings', 'the items'),
    ])


def check_boundary(cc_result, boundary_input):
    parents = {str(r.get('reqId')) for r in boundary_input.get('requirements') or []}
    assumptions = [str(i.get('reqId')) for i in boundary_input.get('items') or [] if i.get('kind') == 'ASSUMPTION']
    # plan 053 P6: what a boundary item may quote - its parent and the items the part is given
    statements = {str(r.get('reqId')): str(r.get('statement') or '') for r in boundary_input.get('requirements') or []}
    item_statements = {str(i.get('reqId')): str(i.get('statement') or '') for i in boundary_input.get('items') or []}

    def checked():
        data = _answer_object(cc_result)
        if set(data) != {'interface', 'environment'}:
            raise ValueError('the answer is not {"interface": [...], "environment": [...]}')
        out = {'interface': [], 'environment': []}
        named = set()
        for name in ('interface', 'environment'):
            raw = _items(data, name, BOUNDARY_FIELDS)
            if not raw:
                raise ValueError("'" + name + "' holds no item")
            for e in raw:
                key = e['key'].strip()
                parent = str(e.get('parent') or '').strip()
                if parent not in parents:
                    raise ValueError(key + ': parent ' + repr(parent) + ' is not a top-level requirement')
                named_here = _strings(e.get('assumptions'), key + ': assumptions')
                if name == 'interface' and named_here:
                    raise ValueError(key + ': an Interface item names no assumption')
                if not set(named_here) <= set(assumptions):
                    raise ValueError(key + ': assumptions ' + str(named_here) + ' are not ASSUMPTION items')
                named.update(named_here)
                refusal = ev.language_refusal(key, e['statement']) or ev.language_refusal(key, e['rationale'])
                if refusal:
                    raise ValueError(refusal)
                evidence = _evidence(e)
                refusal = ev.quote_refusal(key, evidence, dict(item_statements, **{parent: statements[parent]}))
                if refusal:
                    raise ValueError(refusal)
                item = {'key': key, 'parent': parent, 'title': e['title'].strip(), 'statement': e['statement'].strip(),
                        'rationale': e['rationale'].strip(), 'evidence': _evidence_out(evidence)}
                if name == 'environment':
                    item['assumptions'] = named_here
                out[name].append(item)
        unnamed = [a for a in assumptions if a not in named]
        if unnamed:
            raise ValueError('the ASSUMPTION item(s) ' + ', '.join(unnamed) + ' are named by no environment item')
        return out

    return _refused(checked)


# ==================== DESIGN ====================

def requirement_of(design_input, branch):
    for r in design_input.get('requirements') or []:
        if isinstance(r, dict) and r.get('reqId') == (branch or '').strip():
            return r
    raise ValueError("the design input has no top-level requirement '" + str(branch) + "'")


def compose_design(design_input, branch):
    r = requirement_of(design_input, branch)
    lines = [
        'You design how a NEW software system meets ONE top-level requirement - the one below - on its SERVER SIDE: the',
        'algorithm, the policy, the state it keeps. There is no code, and you must not assume any.',
        '',
        'Rules:',
        '- Language-neutral: name no programming language, module, file, class, framework, library or test tool.',
        '- Every design item serves the requirement below; it holds under every interpretation item listed.',
        '- An OPEN_CHOICE item stays open: no design item fixes the dimension it leaves open.',
    ] + DERIVED_EVIDENCE_RULES + [
        '- A title of at most ' + str(ASKED_MAX_TITLE_CHARS) + ' characters. Keys D-1, D-2, ... in order. At least one item.',
        '',
        'The requirement:',
        '',
        str(r.get('reqId')) + ' - ' + str(r.get('title') or '').strip(),
        '  ' + str(r.get('statement') or '').strip(),
        '',
        'The interpretation items:',
    ] + ([_item_line(i) for i in design_input.get('items') or []] or ['- none'])
    others = [x for x in design_input.get('requirements') or [] if x.get('reqId') != r.get('reqId')]
    if others:
        lines += ['', 'The other top-level requirements (read-only - the design must not contradict them):']
        lines += ['- ' + str(x.get('reqId')) + ': ' + str(x.get('statement') or '').strip() for x in others]
    return '\n'.join(lines + [
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object and nothing else:',
        '{"design": [{"key": "D-1", "title": "...", "statement": "...", "rationale": "...", ' + DERIVED_EVIDENCE_SHAPE + '}]}',
        cv.ANSWER_TAIL.replace('the findings', 'the design'),
    ])


def check_design(cc_result, design_input, branch):
    r = requirement_of(design_input, branch)
    # plan 053 P6: what a design item may quote - its branch's requirement and every interpretation item
    sources = {str(i.get('reqId')): str(i.get('statement') or '') for i in design_input.get('items') or []}
    sources[str(r['reqId'])] = str(r.get('statement') or '')

    def checked():
        data = _answer_object(cc_result)
        if set(data) != {'design'}:
            raise ValueError('the answer is not {"design": [...]}')
        raw = _items(data, 'design', DESIGN_FIELDS)
        if not raw:
            raise ValueError("'design' holds no item")
        out = []
        for e in raw:
            key = e['key'].strip()
            refusal = ev.language_refusal(key, e['statement']) or ev.language_refusal(key, e['rationale'])
            if refusal:
                raise ValueError(refusal)
            evidence = _evidence(e)
            refusal = ev.quote_refusal(key, evidence, sources)
            if refusal:
                raise ValueError(refusal)
            out.append({'key': key, 'parent': r['reqId'], 'title': e['title'].strip(), 'statement': e['statement'].strip(),
                        'rationale': e['rationale'].strip(), 'evidence': _evidence_out(evidence)})
        return {'design': out}

    return _refused(checked)


# ==================== the Functions ====================

def run_top_prompt(task, function_code):
    definition_input = _load(io.read_role(task, 'definition-input'), 'definition input')
    subject = (io.read_role(task, 'subject') or '').strip()
    prompt = compose_top(definition_input, subject)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(function_code + ': subject ' + subject + ', ' + str(len(prompt)) + ' chars')


def run_top_check(task, function_code):
    definition_input = _load(io.read_role(task, 'definition-input'), 'definition input')
    subject = (io.read_role(task, 'subject') or '').strip()
    answer = check_top(io.read_role(task, 'cc-result'), definition_input, subject)
    io.write_text(io.output_role(task, 'answer'), json.dumps(answer, ensure_ascii=False))
    print(function_code + ': subject ' + subject + (' REFUSED: ' + ca.excerpt(answer['refused']) if 'refused' in answer
                                                     else ', ' + str(len(answer['requirements'])) + ' requirement(s)'))


def run_boundary_prompt(task, function_code):
    boundary_input = _load(io.read_role(task, 'boundary-input'), 'boundary input')
    prompt = compose_boundary(boundary_input)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(function_code + ': ' + str(len(boundary_input.get('requirements') or [])) + ' top-level requirement(s), '
          + str(len(prompt)) + ' chars')


def run_boundary_check(task, function_code):
    boundary_input = _load(io.read_role(task, 'boundary-input'), 'boundary input')
    answer = check_boundary(io.read_role(task, 'cc-result'), boundary_input)
    io.write_text(io.output_role(task, 'answer'), json.dumps(answer, ensure_ascii=False))
    print(function_code + (': REFUSED: ' + ca.excerpt(answer['refused']) if 'refused' in answer
                           else ': ' + str(len(answer['interface'])) + ' interface, ' + str(len(answer['environment']))
                           + ' environment item(s)'))


def run_design_prompt(task, function_code):
    design_input = _load(io.read_role(task, 'design-input'), 'design input')
    branch = (io.read_role(task, 'branch') or '').strip()
    prompt = compose_design(design_input, branch)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(function_code + ': requirement ' + branch + ', ' + str(len(prompt)) + ' chars')


def run_design_check(task, function_code):
    design_input = _load(io.read_role(task, 'design-input'), 'design input')
    branch = (io.read_role(task, 'branch') or '').strip()
    answer = check_design(io.read_role(task, 'cc-result'), design_input, branch)
    io.write_text(io.output_role(task, 'answer'), json.dumps(answer, ensure_ascii=False))
    print(function_code + ': requirement ' + branch + (' REFUSED: ' + ca.excerpt(answer['refused']) if 'refused' in answer
                                                       else ', ' + str(len(answer['design'])) + ' design item(s)'))
