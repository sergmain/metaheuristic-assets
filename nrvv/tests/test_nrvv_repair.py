# The REPAIR step's prompt and check (nrvv_repair), on the gas-price scenario: a top-level requirement with a design item
# and an Environment item under it, an ASSUMPTION and a READING, and the NEEDs they cite.

import json
import os

import nrvv_repair as wf

N1 = 'The pricing team needs the service to publish gas price updates.'
N2 = 'The pricing team needs each station to settle on the latest price.'
Q1 = 'The pricing team needs to account for sends arriving out of order.'

T1 = {'reqId': 'GASR-10', 'liveReqId': 'GASR-15', 'type': 'TOP_LEVEL', 'interpretation': None, 'section': None,
      'parents': [], 'children': ['GASR-11', 'GASR-12'], 'title': 'Publish',
      'statement': 'The service shall publish every gas price update.',
      'rationale': 'need: GASR-1 r1\nevidence: GASR-1 "publish gas price updates"\npublishes',
      'needs': ['GASR-1'], 'governs': [], 'readings': [],
      'verdict': {'verdict': 'OVER_REACH', 'text': 'every is not in the NEED'}}
D1 = {'reqId': 'GASR-11', 'liveReqId': 'GASR-11', 'type': 'DESIGN', 'interpretation': None, 'section': None,
      'parents': ['GASR-10'], 'children': [], 'title': 'Resend', 'statement': 'The service resends until acknowledged.',
      'rationale': 'resends', 'needs': [], 'governs': [], 'readings': [], 'verdict': None}
X1 = {'reqId': 'GASR-20', 'liveReqId': 'GASR-20', 'type': 'INTERPRETATION', 'interpretation': 'ASSUMPTION',
      'section': 'GASR-30', 'parents': [], 'children': [], 'title': 'Out of order',
      'statement': 'Sends can arrive at a station out of order.',
      'rationale': 'need: GASR-3 r1\ninterpretation: ASSUMPTION\nevidence: GASR-3 "sends arriving out of order"',
      'needs': ['GASR-3'], 'governs': [], 'readings': [], 'verdict': {'verdict': 'JUSTIFIED', 'text': ''}}
X2 = {'reqId': 'GASR-21', 'liveReqId': 'GASR-21', 'type': 'INTERPRETATION', 'interpretation': 'READING',
      'section': 'GASR-30', 'parents': [], 'children': [], 'title': 'Settled',
      'statement': 'Settling is met when the station ends on the latest price.',
      'rationale': 'need: GASR-2 r1\ninterpretation: READING\ngoverns: GASR-2', 'needs': ['GASR-2'], 'governs': ['GASR-2'],
      'readings': [], 'verdict': None}


def need(req_id, statement, kind, covered_by):
    return {'reqId': req_id, 'revision': 1, 'kind': kind, 'title': 't', 'statement': statement, 'coveredBy': covered_by}


C1 = {'id': 'C1',
      'reasons': [{'id': 7, 'kind': 'REQ_CONTRADICTION', 'subject': 'GASR-15', 'counterpart': 'GASR-11',
                   'text': 'publishing every update contradicts resending until acknowledged'}],
      'items': [T1, D1], 'governing': [X2],
      'needs': [need('GASR-1', N1, 'OBLIGATION', []), need('GASR-2', N2, None, ['GASR-13'])],
      'history': [{'repairRunId': 4, 'level': 0,
                   'reasons': [{'kind': 'OVER_REACH', 'subject': 'GASR-10', 'counterpart': None, 'text': 'every',
                                'disposition': 'RECURRED'}],
                   'decisions': [{'reqId': 'GASR-10', 'action': 'CHANGE', 'statement': 'The service shall publish each update.'}],
                   'refusals': ['the REPAIR of component C1 was refused by its check: rule 2']}]}
C2 = {'id': 'C2',
      'reasons': [{'id': 8, 'kind': 'OVER_REACH', 'subject': 'GASR-20', 'counterpart': None, 'text': 'more than the NEED'}],
      'items': [X1], 'governing': [], 'needs': [need('GASR-3', Q1, 'ENVIRONMENT_FACT', [])], 'history': []}
C3 = {'id': 'C3',
      'reasons': [{'id': 9, 'kind': 'NEED_NOT_MET', 'subject': 'GASR-2', 'counterpart': None, 'text': 'nothing settles'}],
      'items': [], 'governing': [], 'needs': [need('GASR-2', N2, None, [])], 'history': []}
CONTEXT = {'snapshotId': 7, 'gateStage': 'BEFORE_CRITERIA', 'components': [C1, C2, C3]}

CHANGE_T1 = {'reqId': 'GASR-15', 'action': 'CHANGE', 'statement': 'The service shall publish gas price updates to stations.',
             'rationale': 'publishes to stations', 'evidence': [{'source': 'GASR-1', 'quote': 'publish gas price updates'}],
             'reason': 'no universal word the NEED does not hold'}
KEEP_D1 = {'reqId': 'GASR-11', 'action': 'KEEP'}


def answer(decisions, add=None):
    return json.dumps({'decisions': decisions, 'add': add or []})


def refusal(raw, chunk='C1', context=None):
    out = wf.checked(raw, context or CONTEXT, chunk + '\n')
    assert set(out.keys()) == {'refused'}, out
    return out['refused']


# ---- the prompt ----

def test_prompt_shows_the_component_the_table_and_ends_with_the_answer_instruction():
    prompt = wf.compose(CONTEXT, C1)
    assert 'REQ_CONTRADICTION on GASR-15 against GASR-11' in prompt
    assert 'Item GASR-10 (TOP_LEVEL, live row GASR-15): Publish' in prompt
    assert 'Newest BACKTRACE verdict: OVER_REACH - every is not in the NEED' in prompt
    assert 'Derived items: GASR-11, GASR-12' in prompt and 'Derived under: GASR-10' in prompt
    assert 'Items they are read under (not to be decided):' in prompt and 'Item GASR-21 (INTERPRETATION READING)' in prompt
    assert 'Covered by: GASR-13' in prompt and 'Covered by: nothing outside these items' in prompt
    assert 'Which side a repair changes:' in prompt
    for finding, change in wf.WHICH_SIDE:
        assert '- ' + finding + ': ' + change + '.' in prompt
    assert 'Earlier iterations of this loop:' in prompt
    assert 'finding OVER_REACH on GASR-10 [RECURRED]: every' in prompt
    assert 'decided CHANGE GASR-10: The service shall publish each update.' in prompt
    assert 'refused: the REPAIR of component C1 was refused by its check: rule 2' in prompt
    assert prompt.rstrip().endswith(wf.cv.ANSWER_TAIL.replace('the findings', 'the repair'))
    assert prompt.index(wf.ANSWER_SHAPE) > prompt.index('Earlier iterations of this loop:')
    assert 'interpretation items only' not in prompt


def test_prompt_of_a_component_with_no_item_and_of_an_interpretation_loop():
    prompt = wf.compose(CONTEXT, C3)
    assert 'Items: none - resolve the findings by additions.' in prompt and 'Earlier iterations' not in prompt
    assert 'interpretation items only' in wf.compose(dict(CONTEXT, gateStage='AFTER_INTERPRETATION'), C2)


# ---- the check: what passes ----

def test_a_change_and_a_keep_pass_in_canonical_form():
    out = wf.checked(answer([CHANGE_T1, KEEP_D1]), CONTEXT, 'C1\n')
    assert out == {'decisions': [
        {'reqId': 'GASR-10', 'action': 'CHANGE', 'statement': 'The service shall publish gas price updates to stations.',
         'rationale': 'publishes to stations', 'evidence': [{'source': 'GASR-1', 'quote': 'publish gas price updates'}],
         'readings': [], 'reason': 'no universal word the NEED does not hold'},
        {'reqId': 'GASR-11', 'action': 'KEEP'}], 'add': []}, out


def test_a_need_not_met_is_repaired_by_an_addition():
    add = [{'kind': 'TOP_LEVEL', 'needs': ['GASR-2'], 'title': 'Settle',
            'statement': 'The service shall make a station settle\non the latest price.', 'rationale': 'r',
            'evidence': [{'source': 'GASR-2', 'quote': 'settle on the latest price'}]}]
    out = wf.checked(answer([], add), CONTEXT, 'C3\n')
    assert out['add'][0]['statement'] == 'The service shall make a station settle on the latest price.', out


def test_a_design_addition_under_the_component_top_level_or_an_earlier_top_level_addition():
    design = {'kind': 'DESIGN', 'parent': 'GASR-15', 'title': 'Latest', 'statement': 'The service sends only the latest price.'}
    assert wf.checked(answer([KEEP_D1, {'reqId': 'GASR-10', 'action': 'KEEP'}], [design]), CONTEXT, 'C1\n')['add'][0]['parent'] == 'GASR-15'
    top = {'kind': 'TOP_LEVEL', 'needs': ['GASR-2'], 'title': 'Settle',
           'statement': 'The service shall make a station settle on the latest price.',
           'evidence': [{'source': 'GASR-2', 'quote': 'settle on the latest price'}]}
    out = wf.checked(answer([], [top, dict(design, parent='A1')]), CONTEXT, 'C3\n')
    assert [a['kind'] for a in out['add']] == ['TOP_LEVEL', 'DESIGN'], out


def test_an_obsolete_whose_needs_stay_covered_passes():
    # GASR-2 is covered by GASR-13 outside the component; the READING GASR-21 is no item of C1, so only GASR-10 and 11
    ctx = {'gateStage': 'BEFORE_CRITERIA', 'components': [dict(C1, items=[dict(T1, needs=['GASR-2']), D1])]}
    out = wf.checked(answer([{'reqId': 'GASR-10', 'action': 'OBSOLETE', 'reason': 'duplicate'}, KEEP_D1]), ctx, 'C1\n')
    assert out['decisions'][0]['action'] == 'OBSOLETE', out


# ---- the check: one test per rule ----

def test_rule_not_a_repair_object():
    assert 'no {"decisions"' in refusal('[]')
    assert 'no {"decisions"' in refusal(json.dumps({'decisions': [], 'verdicts': []}))


def test_rule_every_item_decided_exactly_once_and_nothing_else():
    assert 'no decision on' in refusal(answer([CHANGE_T1]))
    assert 'decided twice' in refusal(answer([CHANGE_T1, KEEP_D1, dict(KEEP_D1, reqId='GASR-11')]))
    assert 'not an item of this component' in refusal(answer([CHANGE_T1, KEEP_D1, {'reqId': 'GASR-21', 'action': 'KEEP'}]))
    assert 'unknown field' in refusal(answer([dict(CHANGE_T1, verdict='x'), KEEP_D1]))
    assert 'none of' in refusal(answer([dict(CHANGE_T1, action='REWRITE'), KEEP_D1]))


def test_rule_the_answer_changes_something():
    assert 'changes nothing' in refusal(answer([{'reqId': 'GASR-10', 'action': 'KEEP'}, KEEP_D1]))


def test_rule_a_change_has_a_statement_and_an_obsolete_a_reason():
    assert "'statement' is not a non-blank string" in refusal(answer([dict(CHANGE_T1, statement=' '), KEEP_D1]))
    assert "'reason' is not a non-blank string" in refusal(answer([{'reqId': 'GASR-10', 'action': 'OBSOLETE'}, KEEP_D1]))


def test_rule_the_evidence_rules_on_a_change():
    assert 'rule 1 (quote)' in refusal(answer([dict(CHANGE_T1, evidence=[{'source': 'GASR-1', 'quote': 'fresh updates'}]), KEEP_D1]))
    assert 'rule 1 (quote)' in refusal(answer([dict(CHANGE_T1, evidence=[]), KEEP_D1]))
    assert 'rule 2' in refusal(answer([dict(CHANGE_T1, statement='The service shall publish every gas price update.'), KEEP_D1]))
    assert 'rule 5 (language)' in refusal(answer([dict(CHANGE_T1, rationale='in Python'), KEEP_D1]))


def test_rule_citations_and_readings_within_the_component():
    assert 'which is no NEED of this component' in refusal(answer([dict(CHANGE_T1, needs=['GASR-9']), KEEP_D1]))
    assert 'cites no NEED' in refusal(answer([dict(CHANGE_T1, needs=[]), KEEP_D1]))
    assert 'is no READING or OPEN_CHOICE item' in refusal(answer([dict(CHANGE_T1, readings=['GASR-11']), KEEP_D1]))
    ok = wf.checked(answer([dict(CHANGE_T1, readings=['GASR-21']), KEEP_D1]), CONTEXT, 'C1\n')
    assert ok['decisions'][0]['readings'] == ['GASR-21'], ok


def test_a_need_cited_as_the_context_shows_it_with_its_revision():
    # Plan 049 Phase 24 (b), project #77, REPAIR #977: the context lists a NEED as "NEED <reqId> r<revision> (...)";
    # an answer citing it so ("GASV7B1-5 r1") was refused as "no NEED of this component" although the NEED is one.
    ok = wf.checked(answer([dict(CHANGE_T1, needs=['GASR-1 r1']), KEEP_D1]), CONTEXT, 'C1\n')
    assert ok['decisions'][0]['needs'] == ['GASR-1'], ok
    add = {'kind': 'INTERPRETATION', 'interpretation': 'READING', 'needs': ['GASR-3'], 'governs': ['GASR-3 r1'],
           'title': 'r', 'statement': 'Arrival order is read as the order sends reach the station.',
           'evidence': [{'source': 'GASR-3', 'quote': 'out of order'}]}
    ok = wf.checked(answer([{'reqId': 'GASR-20', 'action': 'KEEP'}], [add]), CONTEXT, 'C2\n')
    assert ok['add'][0]['governs'] == ['GASR-3'], ok

def test_an_evidence_source_given_as_the_context_shows_the_need():
    # Plan 049 Phase 24 (b) repeat, project #79, REPAIR #1124: "evidence source GASV7B2-6 r1 is neither a NEED it
    # cites nor an item it names in reading" - the source copied from the context's "NEED <reqId> r<revision>".
    sourced = dict(CHANGE_T1, evidence=[{'source': 'GASR-1 r1', 'quote': 'publish gas price updates'}])
    ok = wf.checked(answer([sourced, KEEP_D1]), CONTEXT, 'C1\n')
    assert ok['decisions'][0]['evidence'] == [{'source': 'GASR-1', 'quote': 'publish gas price updates'}], ok

def test_rule_governs_of_an_interpretation_item():
    change = {'reqId': 'GASR-20', 'action': 'CHANGE', 'statement': 'Sends can arrive out of order at a station.',
              'evidence': [{'source': 'GASR-3', 'quote': 'arriving out of order'}]}
    assert wf.checked(answer([change]), CONTEXT, 'C2\n')['decisions'][0]['action'] == 'CHANGE'
    assert 'an ASSUMPTION governs nothing' in refusal(answer([dict(change, governs=['GASR-3'])]), 'C2')
    add = {'kind': 'INTERPRETATION', 'interpretation': 'READING', 'needs': ['GASR-3'], 'title': 'r',
           'statement': 'Arrival order is read as any order.', 'evidence': [{'source': 'GASR-3', 'quote': 'out of order'}]}
    assert 'names what it governs' in refusal(answer([{'reqId': 'GASR-20', 'action': 'KEEP'}], [add]), 'C2')
    assert 'names its kind' in refusal(answer([{'reqId': 'GASR-20', 'action': 'KEEP'}], [dict(add, interpretation='GUESS')]), 'C2')


def test_rule_an_obsolete_keeps_its_needs_covered():
    assert 'leaves NEED GASR-1 uncovered' in refusal(answer([{'reqId': 'GASR-10', 'action': 'OBSOLETE', 'reason': 'r'}, KEEP_D1]))
    add = {'kind': 'TOP_LEVEL', 'needs': ['GASR-1'], 'title': 'Publish',
           'statement': 'The service shall publish gas price updates.',
           'evidence': [{'source': 'GASR-1', 'quote': 'publish gas price updates'}]}
    out = wf.checked(answer([{'reqId': 'GASR-10', 'action': 'OBSOLETE', 'reason': 'r'}, {'reqId': 'GASR-11', 'action': 'OBSOLETE',
                                                                                         'reason': 'r'}], [add]), CONTEXT, 'C1\n')
    assert len(out['add']) == 1, out
    assert 'leaves NEED GASR-3 uncovered' in refusal(answer([{'reqId': 'GASR-20', 'action': 'OBSOLETE', 'reason': 'r'}]), 'C2')


def test_rule_the_parent_of_a_design_addition():
    design = {'kind': 'DESIGN', 'title': 'Latest', 'statement': 'The service sends only the latest price.'}
    keep = [{'reqId': 'GASR-10', 'action': 'KEEP'}, KEEP_D1]
    assert 'names its top-level requirement as parent' in refusal(answer(keep, [design]))
    assert 'no top-level requirement of this component' in refusal(answer(keep, [dict(design, parent='GASR-11')]))
    assert 'is OBSOLETE in this answer' in refusal(answer(
        [{'reqId': 'GASR-10', 'action': 'OBSOLETE', 'reason': 'r'}, KEEP_D1],
        [dict(design, parent='GASR-10'), {'kind': 'TOP_LEVEL', 'needs': ['GASR-1'], 'title': 't',
                                          'statement': 'The service shall publish gas price updates.',
                                          'evidence': [{'source': 'GASR-1', 'quote': 'publish gas price updates'}]}]))
    assert 'is added after it' in refusal(answer([], [dict(design, parent='A2'), {
        'kind': 'TOP_LEVEL', 'needs': ['GASR-2'], 'title': 't', 'statement': 'The service shall make a station settle on the latest price.',
        'evidence': [{'source': 'GASR-2', 'quote': 'settle on the latest price'}]}]), 'C3')
    assert 'a top-level requirement has no parent' in refusal(answer([], [{
        'kind': 'TOP_LEVEL', 'parent': 'GASR-10', 'needs': ['GASR-2'], 'title': 't',
        'statement': 'The service shall make a station settle on the latest price.',
        'evidence': [{'source': 'GASR-2', 'quote': 'settle on the latest price'}]}]), 'C3')
    assert 'rule 5 (language)' in refusal(answer(keep, [dict(design, parent='GASR-10', statement='Written in Java.')]))


def test_rule_an_environment_addition_names_assumptions_only():
    env = {'kind': 'ENVIRONMENT', 'parent': 'GASR-10', 'title': 'Order', 'statement': 'The tests deliver sends out of order.',
           'readings': ['GASR-21']}
    assert 'is no ASSUMPTION item' in refusal(answer([{'reqId': 'GASR-10', 'action': 'KEEP'}, KEEP_D1], [env]))


def test_rule_an_interpretation_loop_changes_interpretation_items_only():
    ctx = dict(CONTEXT, gateStage='AFTER_INTERPRETATION')
    assert 'AFTER_INTERPRETATION loop changes interpretation items only' in refusal(answer([CHANGE_T1, KEEP_D1]), context=ctx)
    add = {'kind': 'TOP_LEVEL', 'needs': ['GASR-2'], 'title': 't', 'statement': 'The service shall make a station settle on the latest price.',
           'evidence': [{'source': 'GASR-2', 'quote': 'settle on the latest price'}]}
    assert 'adds interpretation items only' in refusal(answer([], [add]), 'C3', ctx)


def test_a_chunk_that_is_not_one_component_fails_the_task():
    for chunk in ('', 'C1\nC2', 'C9'):
        try:
            wf.checked(answer([CHANGE_T1, KEEP_D1]), CONTEXT, chunk)
            assert False, chunk
        except ValueError:
            pass


# ---- the Functions' I/O ----

def _task(tmp, metas, inputs, outputs):
    work = tmp / 'work'
    for i, (name, text) in enumerate(inputs.items()):
        p = work / 'variable' / str(i + 1)
        os.makedirs(p.parent, exist_ok=True)
        p.write_text(text, encoding='utf-8')
    return {'workingPath': str(work), 'metas': [{k: v} for k, v in metas.items()],
            'inputs': [{'name': name, 'id': i + 1, 'dataType': 'variable'} for i, name in enumerate(inputs)],
            'outputs': [{'name': name, 'id': 100 + i} for i, name in enumerate(outputs)]}


def test_run_prompt_and_run_check(tmp_path):
    task = _task(tmp_path / 'p', {'variable-for-repair-context': 'repairContext', 'variable-for-components': 'component',
                                  'variable-for-prompt': 'repairPrompt'},
                 {'repairContext': json.dumps(CONTEXT), 'component': 'C1\n'}, ['repairPrompt'])
    wf.run_prompt(task, 'mh.asset.nrvv-repair-prompt_1.0')
    prompt = (tmp_path / 'p' / 'work' / 'artifacts' / '100').read_text(encoding='utf-8')
    assert 'Item GASR-10' in prompt and 'GASR-20' not in prompt

    metas = {'variable-for-cc-result': 'repairResult', 'variable-for-repair-context': 'repairContext',
             'variable-for-components': 'component', 'variable-for-repair': 'repairAnswer'}
    task = _task(tmp_path / 'c', metas, {'repairResult': answer([CHANGE_T1, KEEP_D1]), 'repairContext': json.dumps(CONTEXT),
                                         'component': 'C1\n'}, ['repairAnswer'])
    wf.run_check(task, 'mh.asset.nrvv-repair-check_1.0')
    stored = json.loads((tmp_path / 'c' / 'work' / 'artifacts' / '100').read_text(encoding='utf-8'))
    assert [d['action'] for d in stored['decisions']] == ['CHANGE', 'KEEP']

    task = _task(tmp_path / 'r', metas, {'repairResult': answer([CHANGE_T1]), 'repairContext': json.dumps(CONTEXT),
                                         'component': 'C1\n'}, ['repairAnswer'])
    wf.run_check(task, 'mh.asset.nrvv-repair-check_1.0')
    stored = json.loads((tmp_path / 'r' / 'work' / 'artifacts' / '100').read_text(encoding='utf-8'))
    assert list(stored.keys()) == ['refused'] and 'no decision on' in stored['refused']
