"""The REPAIR step of the convergence loop: one CC session per component - the open hard findings that share
requirements (or a NEED a requirement of theirs cites) - repairs them with small changes: KEEP, CHANGE or OBSOLETE each
item the component names, and ADD what is missing.

The context is mhdg-nrvv.read-repair-context's `repairContext`:
  {"snapshotId", "gateStage", "components": [{"id",
     "reasons": [{"id", "kind", "subject", "counterpart", "text"}],
     "items": [item], "governing": [item],
     "needs": [{"reqId", "revision", "kind", "title", "statement", "coveredBy": [reqId]}],
     "history": [{"repairRunId", "level", "reasons": [{"kind", "subject", "counterpart", "text", "disposition"}],
                  "decisions": [{"reqId", "action", "statement"}], "refusals": [text]}]}]}
  item = {"reqId" (lineage root), "liveReqId", "type" (TOP_LEVEL | DESIGN | INTERFACE | ENVIRONMENT | INTERPRETATION),
          "interpretation", "section", "parents", "children", "title", "statement", "rationale", "needs", "governs",
          "readings", "verdict": {"verdict", "text"} | null}
The chunk is one component id (mh.batch-line-splitter over the output `components`, one line per Task).

CC's answer: {"decisions": [{"reqId", "action": "KEEP|CHANGE|OBSOLETE", "title", "statement", "rationale", "evidence",
"readings", "needs", "governs", "reason"}], "add": [{"kind", "parent", "needs", "interpretation", "governs", "title",
"statement", "rationale", "evidence", "readings"}]}. A check that refuses it writes {"refused": "<rule>"} and its Task
succeeds: mhdg-nrvv.store-repair records one ANSWER_REFUSED and writes nothing for the component. A chunk that is not
exactly one component of the context is a defect of the flow: its ValueError fails the Task.

The rules are NrvvRepairUtils.parseAnswer's (the Dispatcher checks them again), each limited to what the component's
context shows - a NEED cited, an item read under, an ASSUMPTION an Environment item names - so this check refuses at least
what the Dispatcher refuses.

Pure apart from run_prompt / run_check.
"""

import json
import re

import mh_task_io as io
import nrvv_assessment as na
import nrvv_cc_answer as ca
import nrvv_cv_need as cv
import nrvv_evidence as ev

ACTIONS = ('KEEP', 'CHANGE', 'OBSOLETE')
# A NEED as the context lists it - "NEED <reqId> r<revision> (...)" - so an answer may cite it with the revision.
NEED_REF_WITH_REVISION = re.compile(r'(\S+)\s+r\d+')
KINDS = ('TOP_LEVEL', 'DESIGN', 'INTERFACE', 'ENVIRONMENT', 'INTERPRETATION')
UPPER = ('TOP_LEVEL', 'INTERPRETATION')
# the reason kinds that name a missing part - the only ones a TOP_LEVEL or interpretation addition may answer; every
# other reason (a contradiction, OVER_REACH, CONTRADICTS_NEED, RESTS_ON_SUPERSEDED) is resolved by subtraction
MISSING_PART = ('NEED_NOT_MET', 'DESIGN_MISSING', 'ANSWER_REFUSED')
ANSWER_FIELDS = ('decisions', 'add')
DECISION_FIELDS = ('reqId', 'action', 'title', 'statement', 'rationale', 'evidence', 'readings', 'needs', 'governs', 'reason')
ADD_FIELDS = ('kind', 'parent', 'needs', 'interpretation', 'governs', 'title', 'statement', 'rationale', 'evidence', 'readings')

ANSWER_SHAPE = ('{"decisions": [{"reqId": "<an item above>", "action": "KEEP|CHANGE|OBSOLETE", "statement": "<CHANGE: the new'
                ' statement>", "rationale": "<CHANGE: why, in prose>", "evidence": [{"source": "<NEED or item reqId>",'
                ' "quote": "<its words, verbatim>"}], "readings": ["<READING or OPEN_CHOICE reqId>"], "needs": ["<CHANGE:'
                ' the NEEDs it cites, when they change>"], "governs": ["<CHANGE of a READING or OPEN_CHOICE: what it'
                ' governs, when it changes>"], "reason": "<why this action>"}], "add": [{"kind": "TOP_LEVEL|DESIGN|'
                'INTERFACE|ENVIRONMENT|INTERPRETATION", "parent": "<a DESIGN, INTERFACE or ENVIRONMENT item\'s top-level'
                ' requirement>", "needs": ["<NEED reqId>"], "interpretation": "<an INTERPRETATION item: ASSUMPTION|'
                'READING|OPEN_CHOICE>", "governs": ["<NEED reqId or *>"], "title": "...", "statement": "...",'
                ' "rationale": "...", "evidence": [{"source": "...", "quote": "..."}], "readings": ["..."]}]}')

# plan 3.6 - which side a repair changes (decision 11)
WHICH_SIDE = [
    ('REQ_CONTRADICTION, a top-level requirement T vs a design item D',
     'change T when its newest BACKTRACE verdict is not JUSTIFIED or T breaks an evidence rule; otherwise change D'),
    ('REQ_CONTRADICTION, two top-level requirements',
     'change the one that is not JUSTIFIED; both JUSTIFIED - change each to state the condition its governing items give'),
    ('REQ_CONTRADICTION, an interpretation item vs a requirement', 'change the requirement, unless the item is not JUSTIFIED'),
    ('REQ_CONTRADICTION, two design items', 'either; the one with fewer children first'),
    ('OVER_REACH, CONTRADICTS_NEED, RESTS_ON_SUPERSEDED',
     'CHANGE it to what its evidence supports, or OBSOLETE it when every NEED it cites stays covered'),
    ('NEED_NOT_MET', 'ADD a top-level requirement (a derivation NEED) or an interpretation item (a qualifier NEED), or CHANGE'
                     ' an item above that cites the NEED'),
    ('TRACE_ORPHAN', 'CHANGE it to cite its NEED, or OBSOLETE it'),
    ('ANSWER_REFUSED', 'write the refused part again; the refusal is shown'),
]


def context_of(raw):
    """The REPAIR context (mhdg-nrvv.read-repair-context), or a ValueError."""
    try:
        data = json.loads(raw or '')
    except ValueError:
        raise ValueError('the repair context is not JSON: ' + na.excerpt(raw)) from None
    if not isinstance(data, dict) or not isinstance(data.get('components'), list):
        raise ValueError('the repair context has no components list: ' + na.excerpt(raw))
    for c in data['components']:
        if not isinstance(c, dict) or not c.get('id') or not isinstance(c.get('items', []), list):
            raise ValueError('the repair context has a component with no id or no items list')
    return data


def component_of(raw, context):
    """The one component of a chunk - a component of the context - or a ValueError."""
    ids = [line.strip() for line in (raw or '').splitlines() if line.strip()]
    if len(ids) != 1:
        raise ValueError('the chunk names ' + str(len(ids)) + ' components: a REPAIR chunk is one component')
    components = {str(c['id']): c for c in context['components']}
    if ids[0] not in components:
        raise ValueError('the chunk names ' + repr(ids[0]) + ', which is not a component of the repair context')
    return components[ids[0]]


def one_line(text):
    """A text as one line: its lines stripped and joined by a space (NrvvRedefinitionUtils.oneLine)."""
    return ' '.join(line.strip() for line in str(text or '').strip().splitlines() if line.strip())


def _block(lines, indent, text):
    for text_line in str(text or '').strip().splitlines():
        lines.append(indent + text_line)


def _item_lines(lines, it):
    kind = it.get('interpretation')
    head = it['type'] + (' ' + kind if kind else '')
    lines.append('Item ' + str(it['reqId']) + ' (' + head + (', live row ' + str(it['liveReqId'])
                 if it.get('liveReqId') and it['liveReqId'] != it['reqId'] else '') + '): ' + str(it.get('title') or '').strip())
    _block(lines, '  ', it.get('statement'))
    rationale = str(it.get('rationale') or '').strip()
    if rationale:
        lines.append('  Rationale: ' + rationale.replace('\n', ' | '))
    if it.get('parents'):
        lines.append('  Derived under: ' + ', '.join(it['parents']))
    if it.get('children'):
        lines.append('  Derived items: ' + ', '.join(it['children']))
    verdict = it.get('verdict')
    if verdict:
        lines.append('  Newest BACKTRACE verdict: ' + str(verdict.get('verdict'))
                     + (' - ' + str(verdict.get('text')).strip() if str(verdict.get('text') or '').strip() else ''))
    elif it['type'] in UPPER:
        lines.append('  Newest BACKTRACE verdict: not judged at this snapshot')


def compose(context, component):
    """The REPAIR prompt for one component. The answer instruction is the LAST part."""
    lines = [
        'You repair a set of requirements derived from stakeholder NEEDs. The findings below hold at the current',
        'snapshot; your changes are checked again afterwards. Make the smallest changes that resolve every finding.',
        '',
        'Rules:',
        '- Decide every item listed under "Items" exactly once: KEEP, CHANGE (a new statement, rationale and evidence) or',
        '  OBSOLETE. Name no other requirement. Add what is missing under "add".',
        '- A top-level requirement or an interpretation item quotes, in evidence, the words of the NEEDs it cites (or of',
        '  the items it reads under) that it rests on, verbatim, at least two words each. A statement holding each, every,',
        '  all, any, always or never needs a quote holding one of them; a number in a statement appears in a quote.',
        '- A requirement whose cited derivation NEEDs are all COST_OBJECTIVE measures and reports the cost; it bounds',
        '  nothing (no "shall not", "at most", "never", "only", "minimum", no number).',
        '- No statement or rationale names a programming language or a test framework.',
        '- An ASSUMPTION states a fact of the world and governs nothing; a READING or OPEN_CHOICE names the NEEDs it governs',
        '  (or *). A top-level requirement names in readings every READING or OPEN_CHOICE it follows.',
        '- OBSOLETE an item only when every NEED it cites stays covered - by a requirement listed under "Covered by", by',
        '  another item of your answer, or by an addition.',
        '- Resolve by subtraction, in this order: OBSOLETE (when every NEED it cites stays covered), else a CHANGE that',
        '  narrows what the statement claims. Add a top-level requirement or an interpretation item ONLY for a missing',
        '  part - a ' + ', '.join(MISSING_PART) + ' finding below; a contradiction, OVER_REACH, CONTRADICTS_NEED or',
        '  RESTS_ON_SUPERSEDED is never resolved by an addition.',
    ]
    if context.get('gateStage') == 'AFTER_INTERPRETATION':
        lines.append('- This loop repairs the interpretation: change, obsolete and add interpretation items only.')
    lines += ['', 'Which side a repair changes:']
    for finding, change in WHICH_SIDE:
        lines.append('- ' + finding + ': ' + change + '.')
    lines += ['', 'Findings to resolve:']
    for r in component.get('reasons') or []:
        lines.append('- ' + str(r.get('kind')) + ' on ' + str(r.get('subject'))
                     + (' against ' + str(r['counterpart']) if r.get('counterpart') else '') + ': '
                     + str(r.get('text') or '').strip())
    items = component.get('items') or []
    lines += ['', 'Items:' if items else 'Items: none - resolve the findings by additions.']
    for it in items:
        lines.append('')
        _item_lines(lines, it)
    governing = component.get('governing') or []
    if governing:
        lines += ['', 'Items they are read under (not to be decided):']
        for it in governing:
            lines.append('')
            _item_lines(lines, it)
    needs = component.get('needs') or []
    if needs:
        lines += ['', 'NEEDs:']
        for n in needs:
            lines.append('NEED ' + str(n['reqId']) + ' r' + str(n.get('revision')) + ' (' + str(n.get('kind') or 'no kind')
                         + '): ' + str(n.get('statement') or '').strip())
            covered = n.get('coveredBy') or []
            lines.append('  Covered by: ' + (', '.join(covered) if covered else 'nothing outside these items'))
    history = component.get('history') or []
    if history:
        lines += ['', 'Earlier iterations of this loop:']
        for h in history:
            lines.append('- REPAIR run #' + str(h.get('repairRunId')) + ' (level ' + str(h.get('level')) + '):')
            for r in h.get('reasons') or []:
                lines.append('    finding ' + str(r.get('kind')) + ' on ' + str(r.get('subject'))
                             + (' against ' + str(r['counterpart']) if r.get('counterpart') else '')
                             + (' [' + str(r['disposition']) + ']' if r.get('disposition') else '') + ': '
                             + str(r.get('text') or '').strip())
            for d in h.get('decisions') or []:
                lines.append('    decided ' + str(d.get('action')) + ' ' + str(d.get('reqId'))
                             + (': ' + str(d['statement']) if d.get('statement') else ''))
            for t in h.get('refusals') or []:
                lines.append('    refused: ' + str(t).strip())
    return '\n'.join(lines + [
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object - one decision per',
        'item above, "add" empty when nothing is added - and nothing else:',
        ANSWER_SHAPE,
        cv.ANSWER_TAIL.replace('the findings', 'the repair'),
    ])


def _strings(value, where):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ValueError(where + ' is not a list of non-blank strings')
    out = []
    for v in value:
        if v.strip() not in out:
            out.append(v.strip())
    return out


def _string(obj, field, where, required):
    value = obj.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(where + ": '" + field + "' is not a non-blank string")
        return ''
    if not isinstance(value, str):
        raise ValueError(where + ": '" + field + "' is not a string")
    return value.strip()


def _evidence(value, where):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(where + ': evidence is not a list')
    out = []
    for e in value:
        if not isinstance(e, dict) or set(e.keys()) - {'source', 'quote'}:
            raise ValueError(where + ': an evidence entry is not {"source", "quote"}')
        out.append((_string(e, 'source', where + ': evidence', True), _string(e, 'quote', where + ': evidence', True)))
    return out


def _covering_type(need):
    return 'TOP_LEVEL' if ev.is_derivation_subject(need.get('kind')) else 'INTERPRETATION'


def answer_of(cc_result, context, component):
    """CC's answer in canonical form, or a ValueError naming the first broken rule."""
    text = (cc_result or '').strip()
    fenced = na.FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    data = ca.loads(text)
    if not isinstance(data, dict) or set(data.keys()) - set(ANSWER_FIELDS):
        raise ValueError('CC answered no {"decisions": [...], "add": [...]} object: ' + na.excerpt(text))
    items = {str(it['reqId']): it for it in component.get('items') or []}
    known = {}
    for it in (component.get('items') or []) + (component.get('governing') or []):
        known[str(it['reqId'])] = it
        if it.get('liveReqId'):
            known[str(it['liveReqId'])] = it
    # Plan 049 Phase 24 (a), project #84 REPAIR #1482: a superseded row of a component's lineage - the context's
    # "aliases", row -> lineage root - names that item; the readers of a changed item keep its earlier row.
    for alias, lineage in (component.get('aliases') or {}).items():
        if str(lineage) in known and str(alias) not in known:
            known[str(alias)] = known[str(lineage)]
    needs = {str(n['reqId']): n for n in component.get('needs') or []}
    only_items = context.get('gateStage') == 'AFTER_INTERPRETATION'

    def root(ref):
        it = known.get(ref)
        return str(it['reqId']) if it else ref

    def need_ref(ref):
        # Plan 049 Phase 24 (b), project #77 REPAIR #977: "GASV7B1-5 r1", copied from the context's NEED list, is
        # NEED GASV7B1-5; a ref whose reqId is no NEED of this component stays as written, for the rule to name it.
        m = NEED_REF_WITH_REVISION.fullmatch(ref)
        return m.group(1) if m and m.group(1) in needs else ref

    def sourced(evidence):
        # Plan 049 Phase 24 (b) repeat, project #79 REPAIR #1124: an evidence source copied in the same form
        # ("GASV7B2-6 r1") names that NEED as well.
        # Plan 049 Phase 24 (a), project #84: an item named by its live or a superseded row is that item, as in its
        # readings (root), so the source matches the reading it quotes.
        return [(root(need_ref(source)), quote) for source, quote in evidence]

    decisions = {}
    raw_decisions = data.get('decisions') or []
    if not isinstance(raw_decisions, list):
        raise ValueError("'decisions' is not a list")
    for i, d in enumerate(raw_decisions):
        where = 'decision #' + str(i)
        if not isinstance(d, dict):
            raise ValueError(where + ' is not an object')
        extra = [k for k in d.keys() if k not in DECISION_FIELDS]
        if extra:
            raise ValueError(where + ' has an unknown field ' + repr(extra[0]))
        ref = _string(d, 'reqId', where, True)
        req_id = root(ref)
        if req_id not in items:
            raise ValueError(where + ' names ' + ref + ', which is not an item of this component ' + str(sorted(items)))
        if req_id in decisions:
            raise ValueError(req_id + ' is decided twice')
        action = _string(d, 'action', req_id, True).upper()
        if action not in ACTIONS:
            raise ValueError(req_id + ': action ' + repr(action) + ' is none of ' + str(ACTIONS))
        decisions[req_id] = {
            'reqId': req_id, 'action': action,
            'statement': _string(d, 'statement', req_id, action == 'CHANGE'),
            'rationale': _string(d, 'rationale', req_id, False),
            'evidence': sourced(_evidence(d.get('evidence'), req_id)),
            'readings': [root(r) for r in _strings(d.get('readings'), req_id + ': readings')],
            'needs': None if d.get('needs') is None else [need_ref(n) for n in _strings(d.get('needs'), req_id + ': needs')],
            'governs': None if d.get('governs') is None else [need_ref(g) for g in _strings(d.get('governs'), req_id + ': governs')],
            'reason': _string(d, 'reason', req_id, action == 'OBSOLETE'),
        }
    undecided = [r for r in items if r not in decisions]
    if undecided:
        raise ValueError('no decision on ' + str(undecided))
    added = []
    raw_add = data.get('add') or []
    if not isinstance(raw_add, list):
        raise ValueError("'add' is not a list")
    for a in raw_add:
        key = 'A' + str(len(added) + 1)
        if not isinstance(a, dict):
            raise ValueError(key + ' is not an object')
        extra = [k for k in a.keys() if k not in ADD_FIELDS]
        if extra:
            raise ValueError(key + ' has an unknown field ' + repr(extra[0]))
        kind = _string(a, 'kind', key, True).upper()
        if kind not in KINDS:
            raise ValueError(key + ': kind ' + repr(kind) + ' is none of ' + str(KINDS))
        interpretation = _string(a, 'interpretation', key, False).upper()
        added.append({'key': key, 'kind': kind, 'parent': _string(a, 'parent', key, False) or None,
                      'needs': [need_ref(n) for n in _strings(a.get('needs'), key + ': needs')],
                      'interpretation': interpretation or None,
                      'governs': [need_ref(g) for g in _strings(a.get('governs'), key + ': governs')],
                      'title': _string(a, 'title', key, True),
                      'statement': _string(a, 'statement', key, True), 'rationale': _string(a, 'rationale', key, False),
                      'evidence': sourced(_evidence(a.get('evidence'), key)),
                      'readings': [root(r) for r in _strings(a.get('readings'), key + ': readings')]})
    if all(d['action'] == 'KEEP' for d in decisions.values()) and not added:
        raise ValueError('the answer changes nothing - every decision is KEEP and nothing is added')
    if not any(str(r.get('kind')) in MISSING_PART for r in component.get('reasons') or []):
        for a in added:
            if a['kind'] in UPPER:
                raise ValueError(a['key'] + ' adds a ' + a['kind'] + ' item, but no reason of this component is a missing part '
                                 + str(list(MISSING_PART)) + ' - resolve it by OBSOLETE or a narrowing CHANGE')
    obsoleted = {r for r, d in decisions.items() if d['action'] == 'OBSOLETE'}

    def needs_after(r):
        d = decisions[r]
        return d['needs'] if d['action'] == 'CHANGE' and d['needs'] is not None else list(items[r].get('needs') or [])

    def governs_after(r):
        d = decisions[r]
        return d['governs'] if d['action'] == 'CHANGE' and d['governs'] is not None else list(items[r].get('governs') or [])

    def cites_refusal(key, cited):
        if not cited:
            return key + ': cites no NEED'
        for n in cited:
            if n not in needs:
                return key + ': cites ' + n + ', which is no NEED of this component ' + str(sorted(needs))
        return None

    def reading_refusal(key, readings, allowed_kinds):
        for r in readings:
            it = known.get(r)
            if not it or it.get('interpretation') not in allowed_kinds:
                return key + ': reading ' + r + ' is no ' + ' or '.join(allowed_kinds) + ' item of this component'
            if r in obsoleted:
                return key + ': reading ' + r + ' is OBSOLETE in this answer'
        return None

    def top_level_refusal(key, statement, cited, readings, evidence, prose):
        why = cites_refusal(key, cited) or reading_refusal(key, readings, ('READING', 'OPEN_CHOICE'))
        if why:
            return why
        sources = {n: needs[n].get('statement') or '' for n in cited}
        sources.update({r: known[r].get('statement') or '' for r in readings})
        kinds = [needs[n].get('kind') for n in cited if ev.is_derivation_subject(needs[n].get('kind'))]
        rationale = ev.rationale([n + ' r' + str(needs[n].get('revision')) for n in cited], None, [], readings, evidence, [], prose)
        return ev.top_level_refusal(key, statement, rationale, evidence, sources, kinds)

    def interpretation_refusal(key, kind, statement, cited, governs, evidence, prose):
        why = cites_refusal(key, cited)
        if why:
            return why
        if kind == 'ASSUMPTION' and governs:
            return key + ': an ASSUMPTION governs nothing, not ' + str(governs)
        if kind != 'ASSUMPTION' and not governs:
            return key + ': a ' + kind + ' names what it governs'
        for g in governs:
            if g != '*' and g not in needs:
                return key + ': governs ' + g + ', which is no NEED of this component'
        sources = {n: needs[n].get('statement') or '' for n in cited}
        rationale = ev.rationale([n + ' r' + str(needs[n].get('revision')) for n in cited], kind, governs, [], evidence, [], prose)
        return ev.interpretation_refusal(key, kind, statement, rationale, evidence, sources)

    def language_refusal(key, statement, prose):
        return ev.language_refusal(key, statement) or ev.language_refusal(key, prose)

    for r, d in decisions.items():
        it = items[r]
        if only_items and d['action'] != 'KEEP' and it['type'] != 'INTERPRETATION':
            raise ValueError(r + ' is a ' + it['type'] + ' item: an AFTER_INTERPRETATION loop changes interpretation items only')
        if d['action'] != 'CHANGE':
            continue
        statement = one_line(d['statement'])
        if it['type'] == 'TOP_LEVEL':
            why = top_level_refusal(r, statement, needs_after(r), d['readings'], d['evidence'], d['rationale'])
        elif it['type'] == 'INTERPRETATION':
            why = interpretation_refusal(r, it.get('interpretation'), statement, needs_after(r), governs_after(r),
                                         d['evidence'], d['rationale'])
        else:
            why = language_refusal(r, statement, d['rationale'] or it.get('rationale'))
        if why:
            raise ValueError(why)
    top_keys = [a['key'] for a in added if a['kind'] == 'TOP_LEVEL']
    for n, a in enumerate(added):
        key = a['key']
        if only_items and a['kind'] != 'INTERPRETATION':
            raise ValueError(key + ' adds a ' + a['kind'] + ' item: an AFTER_INTERPRETATION loop adds interpretation items only')
        statement = one_line(a['statement'])
        if a['kind'] == 'TOP_LEVEL':
            why = (key + ': a top-level requirement has no parent') if a['parent'] else top_level_refusal(
                key, statement, a['needs'], a['readings'], a['evidence'], a['rationale'])
        elif a['kind'] == 'INTERPRETATION':
            why = ((key + ': an interpretation item names its kind') if a['interpretation'] not in ev.INTERPRETATION_KINDS
                   else (key + ': an interpretation item has no parent') if a['parent']
                   else interpretation_refusal(key, a['interpretation'], statement, a['needs'], a['governs'], a['evidence'],
                                               a['rationale']))
        else:
            parent = a['parent']
            if not parent:
                why = key + ': a ' + a['kind'] + ' item names its top-level requirement as parent'
            elif parent in top_keys:
                why = None if parent in [x['key'] for x in added[:n]] else key + ': parent ' + parent + ' is added after it'
            elif root(parent) not in items or items[root(parent)]['type'] != 'TOP_LEVEL':
                why = key + ': parent ' + parent + ' is no top-level requirement of this component, nor a TOP_LEVEL add'
            elif root(parent) in obsoleted:
                why = key + ': parent ' + root(parent) + ' is OBSOLETE in this answer'
            else:
                why = None
            if not why and a['kind'] == 'ENVIRONMENT':
                why = reading_refusal(key, a['readings'], ('ASSUMPTION',))
            if not why:
                why = language_refusal(key, statement, a['rationale'])
        if why:
            raise ValueError(why)
    for r in obsoleted:
        it = items[r]
        if it['type'] not in UPPER:
            continue
        for n in it.get('needs') or []:
            need = needs.get(n)
            if not need or _covering_type(need) != it['type']:
                continue
            covered = (bool(need.get('coveredBy'))
                       or any(d['action'] != 'OBSOLETE' and items[x]['type'] == it['type'] and n in needs_after(x)
                              for x, d in decisions.items())
                       or any(a['kind'] == it['type'] and n in a['needs'] for a in added))
            if not covered:
                raise ValueError('OBSOLETE ' + r + ' leaves NEED ' + n + ' uncovered - nothing else in or outside the'
                                 + ' component covers it')
    out_decisions = []
    for d in decisions.values():
        o = {'reqId': d['reqId'], 'action': d['action']}
        if d['action'] == 'CHANGE':
            o.update({'statement': one_line(d['statement']), 'rationale': d['rationale'],
                      'evidence': [{'source': s, 'quote': q} for s, q in d['evidence']], 'readings': d['readings']})
            if d['needs'] is not None:
                o['needs'] = d['needs']
            if d['governs'] is not None:
                o['governs'] = d['governs']
        if d['reason']:
            o['reason'] = d['reason']
        out_decisions.append(o)
    out_added = []
    for a in added:
        o = {'kind': a['kind'], 'title': a['title'], 'statement': one_line(a['statement']), 'rationale': a['rationale'],
             'needs': a['needs'], 'governs': a['governs'], 'readings': a['readings'],
             'evidence': [{'source': s, 'quote': q} for s, q in a['evidence']]}
        if a['parent']:
            o['parent'] = a['parent']
        if a['interpretation']:
            o['interpretation'] = a['interpretation']
        out_added.append(o)
    return {'decisions': out_decisions, 'add': out_added}


def checked(cc_result, context, chunk):
    """The checked answer, or {"refused": "<rule>"} when CC's answer breaks a rule. A chunk that is not exactly one
    component of the context is a defect of the flow: component_of's ValueError fails the Task."""
    component = component_of(chunk, context)
    try:
        return answer_of(cc_result, context, component)
    except ValueError as e:
        return {'refused': str(e)}


def run_prompt(task, function_code):
    context = context_of(io.read_role(task, 'repair-context'))
    component = component_of(io.read_role(task, 'components'), context)
    prompt = compose(context, component)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(function_code + ': component ' + str(component['id']) + ', ' + str(len(component.get('reasons') or []))
          + ' reason(s), ' + str(len(component.get('items') or [])) + ' item(s), ' + str(len(prompt)) + ' chars')


def run_check(task, function_code):
    context = context_of(io.read_role(task, 'repair-context'))
    chunk = io.read_role(task, 'components')
    answer = checked(io.read_role(task, 'cc-result'), context, chunk)
    io.write_text(io.output_role(task, 'repair'), json.dumps(answer, ensure_ascii=False))
    component = chunk.strip()
    if 'refused' in answer:
        print(function_code + ': component ' + component + ' REFUSED: ' + ca.excerpt(answer['refused']))
    else:
        print(function_code + ': component ' + component + ', ' + str(len(answer['decisions'])) + ' decision(s), '
              + str(len(answer['add'])) + ' addition(s)')
