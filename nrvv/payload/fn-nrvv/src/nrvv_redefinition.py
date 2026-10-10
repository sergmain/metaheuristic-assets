# Re-definition (plan 045, Phase 18): the two CC prompts that carry a change of the agreed NEEDs into an existing
# definition, and the checks of CC's two answers. Pure: no I/O - the Function scripts nrvv_redefine_prompt /
# nrvv_redefine_check / nrvv_redesign_prompt / nrvv_redesign_check read and write the Variables.
#
# The input is the definition context mhdg-nrvv.read-definition writes (NrvvData.DefinitionContext):
#   needs      [{reqId, revision, title, statement, delta}]   the agreed NEEDs; delta: its current revision must be cited
#   topLevel   [{reqId, liveReqId, title, statement, rationale, citations: ["<NEED> r<rev>"], tracedFrom: [NEED]}]
#   items      [{reqId, liveReqId, kind: design|interface|environment, parents: [top-level reqId], title, statement,
#                rationale}]
#   delta      [NEED reqId]
#
# Answer 1, the top-level requirements:
#   {"topLevel": [{"reqId", "action": "KEEP"},
#                 {"reqId", "action": "CHANGE", "needs": ["<NEED> r<rev>"], "statement"},
#                 {"reqId", "action": "OBSOLETE", "reason"}],
#    "add": [{"key", "needs": ["<NEED> r<rev>"], "title", "statement", "rationale"}]}
#   Every existing top-level requirement exactly once; every citation an agreed NEED at its CURRENT revision, each NEED
#   once per item; every delta NEED cited by a CHANGE or an add; at least one top-level requirement left.
#   A CHANGE keeps the Rationale and re-cites its citation line (need: ...), so the requirement must have one.
#
# Answer 2, the design under the changed and added top-level requirements:
#   {"items": [{"reqId", "action": "KEEP"}, {"reqId", "action": "CHANGE", "statement", "rationale"},
#              {"reqId", "action": "OBSOLETE", "reason"}],
#    "add": [{"key": "D<n>"|"I<n>"|"E<n>", "parent": "<a CHANGED top-level reqId or an add key>", "title", "statement",
#             "rationale"}]}
#   Exactly the items under a CHANGED top-level requirement and under no OBSOLETE one; at least one Interface and one
#   Environment item left.
#   A CHANGE re-words the FIRST paragraph of the item's Rationale with the new one (one line, no double quote), so that
#   paragraph must be there and hold no double quote.
#
# No text may hold a guillemet: the amendment the Dispatcher writes for a CHANGE quotes the new text with them. The
# amendment replaces item 1 and then strikes / inserts in item 2 with a ONE-LINE command: jcons ends a quoted text only
# at the next command, and RG's reason item after a quoted last command would be swallowed into it.
# The Dispatcher checks the same rules again (NrvvRedefinitionUtils.parseTopLevel / parseDesign) before it writes; a
# bad answer fails HERE, where resetting the CC Task repairs it. CC decides every top-level requirement and item, but
# never a NEED: the NEEDs are agreed by people.
#
# Pure: no I/O.

import json

import nrvv_assessment as na

ACTIONS = ('KEEP', 'CHANGE', 'OBSOLETE')
KINDS = {'D': 'design', 'I': 'interface', 'E': 'environment'}
REASON_MAX_BYTES = 2000
ASKED_MAX_TITLE_CHARS = 80


# ---------------------------------------------------------------------------------------------------------- inputs

def context_of(raw):
    """The definition context (mhdg-nrvv.read-definition), or a ValueError."""
    try:
        data = json.loads(raw or '')
    except ValueError:
        raise ValueError('the definition context is not JSON: ' + na.excerpt(raw)) from None
    if not isinstance(data, dict) or any(not isinstance(data.get(k), list) for k in ('needs', 'topLevel', 'items', 'delta')):
        raise ValueError('the definition context has no needs, topLevel, items and delta lists: ' + na.excerpt(raw))
    for k in ('needs', 'topLevel', 'items'):
        if any(not isinstance(x, dict) or not x.get('reqId') for x in data[k]):
            raise ValueError('the definition context has an entry of ' + k + ' with no reqId')
    if not data['topLevel']:
        raise ValueError('the definition context holds no top-level requirement')
    return data


def top_level_of(raw):
    """A checked top-level answer, as nrvv_redefine_check wrote it."""
    data = json.loads(raw or '')
    if not isinstance(data, dict) or not isinstance(data.get('topLevel'), list) or not isinstance(data.get('add'), list):
        raise ValueError('the top-level answer is not a checked {"topLevel": [...], "add": [...]}: ' + na.excerpt(raw))
    return data


# ---------------------------------------------------------------------------------------------------------- prompts

def _needs_text(context):
    blocks = []
    for n in context['needs']:
        mark = '  <-- CHANGED OR NEW: cite "' + n['reqId'] + ' r' + str(n['revision']) + '"' if n.get('delta') else ''
        blocks.append(n['reqId'] + ' r' + str(n['revision']) + ' - ' + (n.get('title') or '') + mark + '\n'
                      + (n.get('statement') or ''))
    return '\n\n'.join(blocks)


def _top_level_text(context):
    blocks = []
    for t in context['topLevel']:
        blocks.append(t['reqId'] + ' - ' + (t.get('title') or '') + '\n'
                      + 'cites: ' + (', '.join(t.get('citations') or []) or 'nothing') + '\n'
                      + 'traced from: ' + (', '.join(t.get('tracedFrom') or []) or 'no NEED') + '\n'
                      + 'statement: ' + (t.get('statement') or '') + '\n'
                      + 'rationale: ' + (t.get('rationale') or '').replace('\n', ' / '))
    return '\n\n'.join(blocks)


def compose_top_level(context):
    """The prompt asking CC what becomes of every top-level requirement after the NEED change."""
    delta = context['delta']
    return '\n'.join([
        'The agreed NEEDs of a software system changed. You carry the change into its TOP-LEVEL REQUIREMENTS.',
        '',
        'A NEED says, in the stakeholders\' words, what they need. A top-level requirement restates NEEDs as what the',
        'system shall do: one verifiable "The service shall ..." statement, never how. Its "needs" cite the',
        'NEED revisions it restates, as "<NEED reqId> r<revision>".',
        '',
        'NEEDs whose current revision no top-level requirement cites yet (the delta): ' + (', '.join(delta) or 'none') + '.',
        '',
        'For EVERY top-level requirement below answer exactly one of:',
        '- KEEP: it still serves its NEEDs as written.',
        '- CHANGE: give the new statement and the NEEDs it cites at their CURRENT revisions; its rationale is kept.',
        '- OBSOLETE: it no longer serves any NEED; give the reason.',
        'Then ADD the top-level requirements the NEEDs now call for and no existing one covers.',
        '',
        'Rules:',
        '- Every NEED of the delta is cited, at its current revision, by at least one CHANGE or ADD.',
        '- Cite only the NEEDs listed below, each at the revision shown, each at most once per requirement.',
        '- Verifiable and language-neutral: no programming language, module, file, class, framework or library.',
        '- You decide alone - nobody answers questions. Begin a rationale with "assumed: <what you decided and why>"',
        '  where you resolve an ambiguity.',
        '- Never use the characters \u00ab or \u00bb.',
        '- An added requirement has a title of at most ' + str(ASKED_MAX_TITLE_CHARS) + ' characters and a key A1, A2, ...',
        '',
        'Store your answer with the result tool as exactly this JSON object, and nothing else:',
        '{"topLevel": [{"reqId": "<reqId>", "action": "KEEP"},',
        '              {"reqId": "<reqId>", "action": "CHANGE", "needs": ["<NEED> r<rev>"], "statement": "..."},',
        '              {"reqId": "<reqId>", "action": "OBSOLETE", "reason": "..."}],',
        ' "add": [{"key": "A1", "needs": ["<NEED> r<rev>"], "title": "...", "statement": "...", "rationale": "..."}]}',
        '',
        'The agreed NEEDs:',
        '',
        _needs_text(context),
        '',
        'The top-level requirements:',
        '',
        _top_level_text(context),
    ])


def items_to_answer(context, top):
    """The design items the design answer names: under a CHANGED top-level requirement and under no OBSOLETE one."""
    changed = {d['reqId'] for d in top['topLevel'] if d['action'] == 'CHANGE'}
    obsoleted = {d['reqId'] for d in top['topLevel'] if d['action'] == 'OBSOLETE'}
    return [i['reqId'] for i in context['items']
            if any(p in changed for p in i.get('parents') or []) and not any(p in obsoleted for p in i.get('parents') or [])]


def compose_design(context, top):
    """The prompt asking CC what becomes of the design under the changed top-level requirements, and what is added."""
    decided = {d['reqId']: d for d in top['topLevel']}
    answer = set(items_to_answer(context, top))
    changed_blocks = []
    for t in context['topLevel']:
        d = decided.get(t['reqId'])
        if d and d['action'] == 'CHANGE':
            changed_blocks.append(t['reqId'] + ' (CHANGED) - ' + (t.get('title') or '') + '\nwas: ' + (t.get('statement') or '')
                                  + '\nnow: ' + d['statement'])
    for a in top['add']:
        changed_blocks.append(a['key'] + ' (ADDED) - ' + a['title'] + '\n' + a['statement'])
    item_blocks = []
    for i in context['items']:
        if i['reqId'] in answer:
            item_blocks.append(i['reqId'] + ' [' + i['kind'] + '] under ' + ', '.join(i.get('parents') or []) + ' - '
                               + (i.get('title') or '') + '\n' + (i.get('statement') or ''))
    others = [i['reqId'] + ' [' + i['kind'] + '] ' + (i.get('title') or '') for i in context['items'] if i['reqId'] not in answer]
    return '\n'.join([
        'Top-level requirements of a software system were changed and added. You carry the change into its DESIGN.',
        '',
        'The design has three kinds of items, each under a top-level requirement:',
        '- design: how the server side meets the requirement - the algorithm, the policy, the state it keeps;',
        '- interface: the boundary every test and the implementation share - each operation the server side offers',
        '  and every port through which it talks to what lies outside it, stated language-neutrally;',
        '- environment: what lies outside the server side and how the tests simulate it, deterministically.',
        '',
        'For EVERY item listed under "Items to answer" answer exactly one of KEEP, CHANGE (a new statement and a',
        'one-line rationale with no double quote) or OBSOLETE (a reason). Then ADD the items the changed and added',
        'requirements need, each under',
        'exactly one parent: a CHANGED requirement\'s reqId or an ADDED requirement\'s key. Name no other item.',
        '',
        'Rules:',
        '- After your answer at least one interface and one environment item remain in the whole design.',
        '- Language-neutral: no programming language, module, file, class, framework or library.',
        '- You decide alone. Begin a rationale with "assumed: ..." where you resolve an ambiguity.',
        '- Never use the characters \u00ab or \u00bb.',
        '- Added keys: D1, D2, ... for design, I1, ... for interface, E1, ... for environment; titles of at most '
        + str(ASKED_MAX_TITLE_CHARS) + ' characters.',
        '',
        'Store your answer with the result tool as exactly this JSON object, and nothing else:',
        '{"items": [{"reqId": "<reqId>", "action": "KEEP"},',
        '           {"reqId": "<reqId>", "action": "CHANGE", "statement": "...", "rationale": "..."},',
        '           {"reqId": "<reqId>", "action": "OBSOLETE", "reason": "..."}],',
        ' "add": [{"key": "D1", "parent": "<reqId or add key>", "title": "...", "statement": "...", "rationale": "..."}]}',
        '',
        'The changed and added top-level requirements:',
        '',
        '\n\n'.join(changed_blocks) or 'none',
        '',
        'Items to answer:',
        '',
        '\n\n'.join(item_blocks) or 'none - answer "items": []',
        '',
        'The other items of the design (not to be named; they stay as they are or go with an obsoleted requirement):',
        '',
        '\n'.join(others) or 'none',
    ])


# ---------------------------------------------------------------------------------------------------------- checks

def check_top_level(cc_result, context):
    """CC's top-level answer, checked and canonical, or a ValueError naming the first broken rule."""
    data = _answer_object(cc_result)
    revisions = {n['reqId']: n['revision'] for n in context['needs']}
    existing = [t['reqId'] for t in context['topLevel']]
    rationales = {t['reqId']: t.get('rationale') or '' for t in context['topLevel']}
    decisions, named = [], set()
    for e in _entries(data, 'topLevel', True):
        req_id = _required(e, 'reqId', "an entry of 'topLevel'")
        if req_id not in existing:
            raise ValueError("'topLevel' names " + req_id + ', which is not a top-level requirement: ' + str(existing))
        if req_id in named:
            raise ValueError('top-level requirement ' + req_id + ' is named twice')
        named.add(req_id)
        action = _action(e, req_id)
        if action == 'KEEP':
            decisions.append({'reqId': req_id, 'action': action})
        elif action == 'CHANGE':
            if not citation_line_of(rationales[req_id]):
                raise ValueError('top-level requirement ' + req_id + ' has no citation line (need: ...) in its Rationale to'
                                 ' re-cite - OBSOLETE it and ADD its successor instead')
            decisions.append({'reqId': req_id, 'action': action, 'needs': _citations(e.get('needs'), req_id, revisions),
                              'statement': _text(e, 'statement', req_id)})
        else:
            decisions.append({'reqId': req_id, 'action': action, 'reason': _reason(e, req_id)})
    unnamed = [r for r in existing if r not in named]
    if unnamed:
        raise ValueError('the answer leaves top-level requirement(s) ' + str(unnamed)
                         + ' unnamed - each takes exactly one of KEEP, CHANGE, OBSOLETE')
    added, keys = [], set()
    for e in _entries(data, 'add', False):
        key = _required(e, 'key', "an entry of 'add'")
        if key in existing or key in keys:
            raise ValueError('the add key ' + key + ' is used twice or is an existing reqId')
        keys.add(key)
        added.append({'key': key, 'needs': _citations(e.get('needs'), key, revisions), 'title': _text(e, 'title', key),
                      'statement': _text(e, 'statement', key), 'rationale': _text(e, 'rationale', key)})
    cited = {c.rsplit(' r', 1)[0] for x in decisions + added for c in x.get('needs', [])}
    uncited = [n for n in context['delta'] if n not in cited]
    if uncited:
        raise ValueError('the answer leaves delta NEED(s) ' + str(uncited)
                         + ' uncited - each is cited at its current revision by a CHANGE or an add')
    if all(d['action'] == 'OBSOLETE' for d in decisions) and not added:
        raise ValueError('the answer obsoletes every top-level requirement and adds none')
    return {'topLevel': decisions, 'add': added}


def check_design(cc_result, context, top):
    """CC's design answer, checked against the context and the checked top-level answer, or a ValueError."""
    data = _answer_object(cc_result)
    answer = items_to_answer(context, top)
    obsoleted_tops = {d['reqId'] for d in top['topLevel'] if d['action'] == 'OBSOLETE'}
    items = {i['reqId']: i for i in context['items']}
    decisions, named = [], set()
    for e in _entries(data, 'items', True):
        req_id = _required(e, 'reqId', "an entry of 'items'")
        if req_id not in answer:
            item = items.get(req_id)
            why = (', which is not a design, Interface or Environment item' if item is None
                   else ', which goes OBSOLETE with its top-level requirement - do not name it'
                   if any(p in obsoleted_tops for p in item.get('parents') or [])
                   else ', which is under no CHANGED top-level requirement')
            raise ValueError("'items' names " + req_id + why + '; the items to answer: ' + str(answer))
        if req_id in named:
            raise ValueError('item ' + req_id + ' is named twice')
        named.add(req_id)
        action = _action(e, req_id)
        if action == 'KEEP':
            decisions.append({'reqId': req_id, 'action': action})
        elif action == 'CHANGE':
            old = first_paragraph(items[req_id].get('rationale'))
            if not old or '"' in old:
                raise ValueError('item ' + req_id + "'s Rationale " + ('is empty' if not old else 'holds a double quote')
                                 + ' - its CHANGE cannot re-word it; OBSOLETE it and ADD its successor instead')
            rationale = ' '.join(line.strip() for line in _text(e, 'rationale', req_id).splitlines() if line.strip())
            if '"' in rationale:
                raise ValueError(req_id + "'s rationale holds a double quote - the amendment quotes it with them")
            decisions.append({'reqId': req_id, 'action': action, 'statement': _text(e, 'statement', req_id),
                              'rationale': rationale})
        else:
            decisions.append({'reqId': req_id, 'action': action, 'reason': _reason(e, req_id)})
    unnamed = [r for r in answer if r not in named]
    if unnamed:
        raise ValueError('the answer leaves item(s) ' + str(unnamed) + ' unnamed - each item under a CHANGED top-level'
                         ' requirement takes exactly one of KEEP, CHANGE, OBSOLETE')
    parents = [d['reqId'] for d in top['topLevel'] if d['action'] == 'CHANGE'] + [a['key'] for a in top['add']]
    added, keys = [], set()
    for e in _entries(data, 'add', False):
        key = _required(e, 'key', "an entry of 'add'")
        if key[0] not in KINDS:
            raise ValueError('the add key ' + key + ' does not start with D, I or E')
        if key in items or key in parents or key in keys:
            raise ValueError('the add key ' + key + ' is used twice or is an existing reqId')
        keys.add(key)
        parent = _required(e, 'parent', key)
        if parent not in parents:
            raise ValueError(key + " names parent '" + parent + "', which is neither a CHANGED top-level requirement nor"
                             ' an added one: ' + str(parents))
        added.append({'key': key, 'parent': parent, 'title': _text(e, 'title', key), 'statement': _text(e, 'statement', key),
                      'rationale': _text(e, 'rationale', key)})
    obsoleted_items = {d['reqId'] for d in decisions if d['action'] == 'OBSOLETE'}
    remaining = {}
    for i in context['items']:
        if not any(p in obsoleted_tops for p in i.get('parents') or []) and i['reqId'] not in obsoleted_items:
            remaining[i['kind']] = remaining.get(i['kind'], 0) + 1
    for a in added:
        kind = KINDS[a['key'][0]]
        remaining[kind] = remaining.get(kind, 0) + 1
    if not remaining.get('interface') or not remaining.get('environment'):
        raise ValueError('a definition keeps at least one Interface and one Environment item; after this answer '
                         + str(remaining.get('interface', 0)) + ' Interface and ' + str(remaining.get('environment', 0))
                         + ' Environment item(s) remain')
    return {'items': decisions, 'add': added}


def to_json(answer):
    """A checked answer as the single-line JSON mhdg-nrvv.store-redefinition reads."""
    return json.dumps(answer, ensure_ascii=False, separators=(',', ':'))


def citation_line_of(rationale):
    """The first `need:` line of a Rationale, stripped; None when there is none."""
    for line in (rationale or '').splitlines():
        if line.strip().lower().startswith('need:'):
            return line.strip()
    return None


def first_paragraph(rationale):
    """The first non-blank paragraph of a Rationale, stripped; '' when there is none."""
    for line in (rationale or '').splitlines():
        if line.strip():
            return line.strip()
    return ''


# ---------------------------------------------------------------------------------------------------------- helpers

def _answer_object(cc_result):
    text = (cc_result or '').strip()
    fenced = na.FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError('CC answered something that is not JSON: ' + na.excerpt(text)) from None
    if not isinstance(data, dict):
        raise ValueError('CC answered no JSON object: ' + na.excerpt(text))
    return data


def _entries(data, field, required):
    raw = data.get(field)
    if raw is None and not required:
        return []
    if not isinstance(raw, list):
        raise ValueError("'" + field + "' is missing or not an array")
    for e in raw:
        if not isinstance(e, dict):
            raise ValueError("an entry of '" + field + "' is not an object: " + na.excerpt(json.dumps(e)))
    return raw


def _action(e, who):
    action = e.get('action')
    if not isinstance(action, str) or action.strip() not in ACTIONS:
        raise ValueError(who + " has action '" + str(action) + "' - KEEP, CHANGE or OBSOLETE")
    return action.strip()


def _required(e, field, who):
    value = e.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(who + ' has no ' + field)
    return value.strip()


def _text(e, field, who):
    value = _required(e, field, who)
    if '\u00ab' in value or '\u00bb' in value:
        raise ValueError(who + "'s " + field + ' holds a guillemet (\u00ab or \u00bb) - the amendment document quotes with them')
    return value


def _reason(e, who):
    value = _text(e, 'reason', who)
    if len(value.encode('utf-8')) > REASON_MAX_BYTES:
        raise ValueError(who + "'s reason is longer than " + str(REASON_MAX_BYTES) + ' UTF-8 bytes')
    return value


def _citations(raw, who, revisions):
    if not isinstance(raw, list) or not raw:
        raise ValueError(who + ' cites no NEED - "needs" is a non-empty array of "<reqId> r<revision>"')
    out, seen = [], set()
    for c in raw:
        parts = c.strip().rsplit(' r', 1) if isinstance(c, str) else []
        if len(parts) != 2 or not parts[0].strip() or not parts[1].isdigit() or int(parts[1]) < 1:
            raise ValueError(who + " cites '" + str(c) + "', which does not read \"<reqId> r<revision>\"")
        need, revision = parts[0].strip(), int(parts[1])
        if need not in revisions:
            raise ValueError(who + ' cites ' + need + ' r' + str(revision) + ', which is not an agreed NEED at the snapshot: '
                             + str(sorted(revisions)))
        if revisions[need] != revision:
            raise ValueError(who + ' cites ' + need + ' r' + str(revision) + ', which is not the current revision of '
                             + need + ' (r' + str(revisions[need]) + ')')
        if need in seen:
            raise ValueError(who + ' cites ' + need + ' twice')
        seen.add(need)
        out.append(need + ' r' + str(revision))
    return out
