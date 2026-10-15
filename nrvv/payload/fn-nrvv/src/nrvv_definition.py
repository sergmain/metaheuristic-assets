# The DEFINITION stage of NRVV (plan 043, Phase 8): the two CC prompts that turn NEED records into a definition, and
# the checks of CC's two answers. Pure: no IO - the Function scripts nrvv_decompose_prompt / nrvv_decompose_check /
# nrvv_design_prompt / nrvv_design_check read and write the Variables.
#
# Stage 1 of 2 (plan 043, decision 1): NEEDs in, a definition out -
#   decomposition  {"requirements": [{"key": "R1", "needs": ["N-1"], "title", "statement", "rationale"}]}
#                  obligations: WHAT the system must do, one per statement, each naming the NEED codes it restates
#   design         {"design": [D items], "interface": [I items], "environment": [E items]}, every item
#                  {"key", "parent": "<an R key>", "title", "statement", "rationale"}: HOW the server side meets the
#                  obligations, the boundary every test and the implementation share, and what lies outside the
#                  server side and is simulated by the tests
#
# The checks are the rules mhdg-nrvv.store-definition re-checks in the Dispatcher (NrvvDefinitionUtils.parse, Java):
# keys unique across both answers and starting with the letter of their list (R, D, I, E); every R item names at least
# one NEED and only NEEDs of the run; every NEED is restated by at least one R item; every D, I and E item names an R
# key as its ONE parent (DERIVATION is a tree, decision 6); at least one R, one I and one E item; key, title, statement
# and rationale non-blank. A broken rule fails the check's Task with the rule, before anything reaches RG.
#
# CC DECIDES (decision 2): no question goes to the user. Every interpretation CC makes - an ambiguity resolved, a word
# made measurable - is written into a statement, and stated in that item's rationale as `assumed: ...`.
#
# Plan 047 Phase 14 (decision 14) narrows that for the top-level requirements: a statement holds only what the NEEDs
# state or what holds under every reading of them; an ambiguity is recorded, not resolved - one rationale line
# `ambiguity: <what>` each (the Dispatcher stores one AMBIGUITY finding per line, Phase 15); no number, duration, rate
# or limit the NEEDs do not state enters a statement; a COST_OBJECTIVE NEED becomes an obligation to measure and report
# that cost, never a bound. `assumed:` stays for the design, Interface and Environment items only. A NEED shows its
# clause kind when it has one, and the answer instruction is the LAST part of each prompt - CC acts on what it reads
# last.
#
# LANGUAGE-NEUTRAL (decision 8): one definition feeds several implementations, so no item names a programming
# language, a module, a file or a framework; the Python binding lives in the test and implementation prompts.
#
# Plan 045 Phase 10: the NEEDs may also be the agreed NEEDs mhdg-nrvv.read-agreed-needs writes - {reqId, revision,
# title, statement, parentReqId} - and a NEED is then named by its reqId wherever it was named by its code: in the
# prompts, in an obligation's "needs" and in the check. A NEED with a reqId is named by it; one without, by its code
# (the v3 shape of mhdg-nrvv.read-needs, until plan 045 Phase 15).

import json
import re
import nrvv_cc_answer as ca

# A model sometimes wraps JSON in a markdown fence. That, and only that, is unwrapped (as the other checks do).
FENCE = re.compile(r'^```[A-Za-z]*\s*\n(.*)\n```$', re.DOTALL)
EXCERPT = 300

ASKED_MAX_TITLE_CHARS = 80

# Plan 047 Phase 15 (decision 14): an assumed: item anywhere in a top-level requirement's rationale, any case - the
# Dispatcher refuses it too (NrvvDefinitionUtils.assumedRefusal, 06.015.130); design items may assume.
ASSUMED = re.compile(r'(?i)\bassumed:')


def excerpt(text):
    text = text or ''
    return text if len(text) <= EXCERPT else text[:EXCERPT] + '...'


# ---------------------------------------------------------------------------------------------------------- NEEDs

def parse_needs(needs_json):
    """The NEEDs of the run, as mhdg-nrvv.read-needs wrote them: a list of {code, revision, title, statement}, in code
    order. A ValueError when the text is not such a list or names no NEED.

    Plan 045 Phase 10: or as mhdg-nrvv.read-agreed-needs wrote them, each NEED named by its reqId (need_id)."""
    try:
        needs = json.loads(needs_json or '')
    except ValueError:
        raise ValueError('needs is not JSON: ' + excerpt(needs_json)) from None
    if not isinstance(needs, list) or not needs:
        raise ValueError('needs is not a non-empty JSON array: ' + excerpt(needs_json))
    for n in needs:
        if not isinstance(n, dict) or not need_id(n) or not _text(n.get('statement')):
            raise ValueError('a NEED of needs has no code or no statement: ' + excerpt(json.dumps(n)))
    return needs


def need_id(need):
    """The name a NEED goes by: its reqId when it has one (an agreed NEED, plan 045), else its code (v3); None when it
    has neither."""
    return _text(need.get('reqId')) or _text(need.get('code'))


def needs_text(needs):
    """The NEEDs as a prompt shows them: code, revision and title, then the statement.

    Plan 047 Phase 14: a NEED with a clause kind (an agreed NEED of an analysed Expectation) shows it after its revision;
    one without keeps the v4 line."""
    blocks = []
    for n in needs:
        kind = _text(n.get('kind'))
        blocks.append(need_id(n) + ' (revision ' + str(n.get('revision')) + (', ' + kind if kind else '') + ') - '
                      + (_text(n.get('title')) or '') + '\n' + _text(n.get('statement')))
    return '\n\n'.join(blocks)


# ---------------------------------------------------------------------------------------------------------- prompts

def compose_decompose_prompt(needs):
    """The prompt asking CC for the obligations that restate the NEEDs."""
    return '\n'.join([
        'You turn the NEEDs of stakeholders into the REQUIREMENTS of a software system.',
        '',
        'A NEED says, in the stakeholders\' words, what they need. A requirement restates it as an obligation of the',
        'system: what the system shall do - never how. You define a NEW system: there is no code, and you must not',
        'assume any.',
        '',
        'Rules:',
        '- One obligation per requirement: one verifiable "The service shall ..." statement. Split a NEED that asks for',
        '  several things into several requirements.',
        '- Every requirement names, in "needs", the code(s) of the NEED(s) it restates; every NEED below is restated by',
        '  at least one requirement. Name no other code.',
        '- Verifiable: an observer can decide from outside whether the system meets it.',
        '- Language-neutral: name no programming language, module, file, class, framework or library.',
        # plan 047 Phase 14 (decision 14): was "Where a NEED is ambiguous or a word must be made measurable, decide,
        # write the decision into the statement" - which wrote a deadline and a send spacing r1 never stated
        '- You decide alone - nobody answers questions.',
        '- A statement holds only what the NEEDs state, or what holds under EVERY reading of them.',
        '- Where a NEED is ambiguous, choose no reading: write the statement so that it holds under every reading,',
        '  and add to its rationale one line "ambiguity: <what is ambiguous>" per ambiguity.',
        '- No number, duration, rate or limit the NEEDs do not state appears in a statement - not as a deadline, a',
        '  spacing, a count or a bound.',
        '- A COST_OBJECTIVE NEED (a cost the stakeholders want kept low) is restated as an obligation to measure and',
        '  report that cost - never as a bound on it.',
        '- A rationale never begins with "assumed:" - a requirement that restates NEEDs assumes nothing. The rationale',
        '  says why the requirement follows from its NEED(s).',
        '- A title of at most ' + str(ASKED_MAX_TITLE_CHARS) + ' characters.',
        '- Keys R1, R2, R3, ... in order.',
        '',
        'The NEEDs:',
        '',
        needs_text(needs),
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object, and nothing else:',
        '{"requirements": [{"key": "R1", "needs": ["' + need_id(needs[0]) + '"], "title": "<title>", "statement": "<the obligation>",'
        ' "rationale": "<rationale>"}]}',
        'Print nothing - neither the requirements nor any explanation: only what the tool stores reaches the pipeline.',
    ])


def compose_design_prompt(needs, decomposition):
    """The prompt asking CC for the design, the Interface and the Environment that meet the checked obligations."""
    obligations = '\n\n'.join(r['key'] + ' - ' + r['title'] + ' (restates ' + ', '.join(r['needs']) + ')\n'
                              + r['statement'] for r in decomposition['requirements'])
    return '\n'.join([
        'You design a NEW software system that meets the requirements (obligations) below, which restate the NEEDs',
        'below. There is no code, and you must not assume any.',
        '',
        'The system is the SERVER SIDE: the part that will be implemented. Everything outside it - its clients, and the',
        'transport between them and the server side - is not implemented: the tests SIMULATE it, deterministically.',
        '',
        'Answer three lists, every item under exactly ONE obligation, named by its key in "parent":',
        '- "design": how the server side meets the obligations - the algorithm, the policy, the state it keeps. Zero or',
        '  more items.',
        '- "interface": the boundary every test and the implementation share - each operation the server side offers',
        '  (its name, parameters and result) and every port through which the server side sends to, or learns from,',
        '  what lies outside it. Stated language-neutrally: names, parameters, results and when each is called - no',
        '  programming language. At least one item.',
        '- "environment": what lies outside the server side and how the tests simulate it - the clients\' behaviour,',
        '  the transport\'s ordering, delivery and acknowledgement rules, and what a test can observe. The simulation is',
        '  deterministic: any randomness is seeded, there is no wall clock and no real network. At least one item.',
        '',
        'Rules:',
        '- Language-neutral: name no programming language, module, file, class, framework or library.',
        # plan 045 Phase 36 (2026-10-10): haiku answered "parent": "R1, R2" for an item serving two obligations - the
        # check refuses that (DERIVATION is a tree, decision 6); the rule is now stated where the answer is written
        '- "parent" is ONE obligation key, exactly as written (for example "R1") - never a list and never several keys.',
        '  An item that serves several obligations goes under the one it serves most directly.',
        # plan 047 Phase 28 (section 3.4): runs simulated lost and dropped sends that no NEED states
        '- The environment simulates only what the NEEDs state about what lies outside the server side.',
        '  A loss, a duplicate, an outage or a crash that no NEED states is not simulated - neither in the base',
        '  scenario nor in a separate one.',
        '- You decide alone - nobody answers questions. Begin the rationale of an item that resolves an ambiguity with',
        '  "assumed: <what you decided and why>".',
        '- A title of at most ' + str(ASKED_MAX_TITLE_CHARS) + ' characters.',
        '- Keys D1, D2, ... for design, I1, I2, ... for interface, E1, E2, ... for environment.',
        '',
        'The NEEDs:',
        '',
        needs_text(needs),
        '',
        'The obligations:',
        '',
        obligations,
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object, and nothing else:',
        '{"design": [{"key": "D1", "parent": "R1", "title": "<title>", "statement": "<statement>",'
        ' "rationale": "<rationale>"}],',
        ' "interface": [{"key": "I1", "parent": "R1", "title": "...", "statement": "...", "rationale": "..."}],',
        ' "environment": [{"key": "E1", "parent": "R1", "title": "...", "statement": "...", "rationale": "..."}]}',
        'Print nothing - neither the design nor any explanation: only what the tool stores reaches the pipeline.',
    ])


# ---------------------------------------------------------------------------------------------------------- checks

def check_decomposition(cc_result, needs):
    """CC's decomposition answer, checked - {"requirements": [...]} with every field stripped - or a ValueError
    naming the broken rule."""
    data = _answer_object(cc_result, '{"requirements": [...]}')
    requirements = _items(data, 'requirements', 'R', obligations=True)
    if not requirements:
        raise ValueError('no obligation: "requirements" is empty')
    _unique_keys(requirements)
    codes = [need_id(n) for n in needs]
    named = set()
    for r in requirements:
        if not r['needs']:
            raise ValueError('obligation ' + r['key'] + ' names no NEED')
        for code in r['needs']:
            if code not in codes:
                raise ValueError('obligation ' + r['key'] + " names NEED '" + code + "', which is not one of the NEEDs: "
                                 + str(codes))
            named.add(code)
    unanswered = [c for c in codes if c not in named]
    if unanswered:
        raise ValueError('no obligation restates NEED(s) ' + str(unanswered))
    for r in requirements:
        assumed_refusal(r['key'], r['rationale'])
    return {'requirements': requirements}


def assumed_refusal(key, rationale):
    """Plan 047 Phase 15: a ValueError when the rationale of top-level requirement `key` holds an assumed: item."""
    if ASSUMED.search(rationale or ''):
        raise ValueError('top-level requirement ' + key + " holds an 'assumed:' item in its rationale - a top-level"
                         ' requirement assumes nothing: state what holds under every reading of its NEEDs and record each'
                         " open ambiguity as a line 'ambiguity: <what>'")


def check_design(cc_result, decomposition):
    """CC's design answer, checked against the checked decomposition - {"design", "interface", "environment"} with
    every field stripped - or a ValueError naming the broken rule."""
    data = _answer_object(cc_result, '{"design": [...], "interface": [...], "environment": [...]}')
    design = _items(data, 'design', 'D', obligations=False)
    interface = _items(data, 'interface', 'I', obligations=False)
    environment = _items(data, 'environment', 'E', obligations=False)
    _unique_keys(decomposition['requirements'] + design + interface + environment)
    r_keys = [r['key'] for r in decomposition['requirements']]
    for item in design + interface + environment:
        if item['parent'] not in r_keys:
            raise ValueError(item['key'] + " names parent '" + str(item['parent']) + "', which is not an obligation's key: "
                             + str(r_keys))
    if not interface or not environment:
        raise ValueError('a definition needs at least one Interface and one Environment item; got '
                         + str(len(interface)) + ' / ' + str(len(environment)))
    return {'design': design, 'interface': interface, 'environment': environment}


def to_json(answer):
    """A checked answer as the single-line JSON mhdg-nrvv.store-definition reads."""
    return json.dumps(answer, ensure_ascii=False, separators=(',', ':'))


def parse_decomposition(text):
    """A checked decomposition as the decompose check wrote it (the design prompt's and check's input)."""
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get('requirements'), list):
        raise ValueError('decomposition is not a checked {"requirements": [...]}: ' + excerpt(text))
    return data


def _answer_object(cc_result, shape):
    text = (cc_result or '').strip()
    fenced = FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    data = ca.loads(text)
    if not isinstance(data, dict):
        raise ValueError('CC answered no JSON object ' + shape + ': ' + excerpt(text))
    return data


def _items(data, name, letter, obligations):
    raw = data.get(name)
    if not isinstance(raw, list):
        raise ValueError("'" + name + "' is missing or not an array")
    items = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("an item of '" + name + "' is not an object: " + excerpt(json.dumps(entry)))
        key = _required(entry, 'key', name)
        if not key.startswith(letter):
            raise ValueError("key '" + key + "' of '" + name + "' does not start with " + letter)
        item = {'key': key}
        if obligations:
            codes = entry.get('needs')
            if codes is not None and not isinstance(codes, list):
                raise ValueError('obligation ' + key + ' has "needs" that is not an array')
            cleaned = []
            for c in codes or []:
                if not _text(c):
                    raise ValueError('obligation ' + key + ' names a blank NEED code')
                if c.strip() not in cleaned:
                    cleaned.append(c.strip())
            item['needs'] = cleaned
        else:
            item['parent'] = _text(entry.get('parent'))
        for field in ('title', 'statement', 'rationale'):
            item[field] = _required(entry, field, name)
        items.append(item)
    return items


def _unique_keys(items):
    seen = set()
    for item in items:
        if item['key'] in seen:
            raise ValueError("key '" + item['key'] + "' is used twice")
        seen.add(item['key'])


def _required(entry, field, name):
    value = _text(entry.get(field))
    if not value:
        raise ValueError("an item of '" + name + "' has no " + field + ': ' + excerpt(json.dumps(entry)))
    return value


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None
