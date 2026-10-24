# The NEED checks of NRVV v5 (plan 047, Phase 10): the CONTRADICTION and QUALITY prompts - their tails and what they
# list - and every refusal of the shared check, the mirrored pair stored once.

import json

import pytest

import nrvv_cv_need as cv
import nrvv_cv_need_backtrace as backtrace
import nrvv_cv_need_contradiction as contradiction
import nrvv_cv_need_feasibility as feasibility
import nrvv_cv_need_quality as quality

NEEDS = [
    {'reqId': 'GAS-2', 'revision': 1, 'title': 'Settle', 'statement': 'The pricing team needs each station to settle\non the latest price.',
     'parentReqId': None, 'kind': 'OBLIGATION'},
    {'reqId': 'GAS-6', 'revision': 1, 'title': 'Keep first', 'statement': 'The pricing team needs each station to keep the first price.',
     'parentReqId': None, 'kind': 'OBLIGATION'},
    {'reqId': 'GAS-7', 'revision': 1, 'title': 'Costs', 'statement': 'Sending has a cost.', 'parentReqId': None,
     'kind': 'COST_OBJECTIVE'},
    {'reqId': 'GAS-9', 'revision': 1, 'title': 'v4 NEED', 'statement': 'No kind line.', 'parentReqId': None},
]


def answer(*findings):
    return json.dumps({'findings': list(findings)})


def finding(kind, subject, counterpart=None, text='what is wrong'):
    f = {'kind': kind, 'subject': subject, 'text': text}
    if counterpart is not None:
        f['counterpart'] = counterpart
    return f


# ==================== prompts ====================

@pytest.mark.parametrize('module', [contradiction, quality])
def test_prompt_ends_with_the_answer_instruction(module):
    lines = module.compose(NEEDS).split('\n')
    assert lines[-1] == cv.ANSWER_TAIL
    assert lines[-2] == cv.ANSWER_SHAPE
    assert lines[-3].startswith('Answer by calling the mh_cc_store_result tool exactly once')
    assert 'Print nothing' in lines[-1]


@pytest.mark.parametrize('module', [contradiction, quality])
def test_prompt_lists_every_need_with_its_kind(module):
    prompt = module.compose(NEEDS)
    assert 'NEED GAS-2 (OBLIGATION): Settle' in prompt
    assert '  on the latest price.' in prompt, 'a multi-line statement keeps its lines'
    assert 'NEED GAS-7 (COST_OBJECTIVE): Costs' in prompt
    assert 'NEED GAS-9: v4 NEED' in prompt, 'a NEED without a kind is listed without one'
    assert 'A NEED without a kind is an OBLIGATION.' in prompt
    assert prompt.index('NEED GAS-9') < prompt.index('mh_cc_store_result'), 'the instruction is LAST'


def test_prompt_without_needs():
    assert 'The project has no agreed NEED.' in contradiction.compose([])


def test_contradiction_prompt_asks_for_the_minimal_witness_and_spares_costs():
    prompt = contradiction.compose(NEEDS)
    assert 'minimal witness situation' in prompt
    assert 'COST_OBJECTIVE NEED against any other NEED' in prompt
    assert 'No finding at all is a valid answer' in prompt


def test_quality_prompt_names_its_five_kinds_and_leaves_contradictions_out():
    prompt = quality.compose(NEEDS)
    for kind in quality.KINDS:
        assert '- ' + kind + ':' in prompt, kind
    assert 'cannot both hold are not a quality matter' in prompt


# ==================== check ====================

def test_contradiction_check_keeps_one_of_a_mirrored_pair():
    out = cv.findings_of(answer(finding('CONTRADICTION', 'GAS-6', 'GAS-2', 'first'), finding('CONTRADICTION', 'GAS-2', 'GAS-6', 'mirror')),
                         NEEDS, contradiction.KINDS, contradiction.PAIR_KINDS)['findings']
    assert out == [{'kind': 'CONTRADICTION', 'subject': 'GAS-6', 'counterpart': 'GAS-2', 'text': 'first'}]


def test_check_unwraps_one_fence_and_accepts_no_finding():
    assert cv.findings_of('```json\n{"findings": []}\n```', NEEDS, contradiction.KINDS, contradiction.PAIR_KINDS) == {'findings': []}


def test_quality_check_single_need_kinds_and_a_redundancy():
    out = cv.findings_of(answer(finding('VAGUE_TERM', 'GAS-2', text='"settle" is not checkable'),
                                finding('VAGUE_TERM', 'GAS-2', text='repeated'),
                                finding('REDUNDANCY', 'GAS-2', 'GAS-6')),
                         NEEDS, quality.KINDS, quality.PAIR_KINDS)['findings']
    assert [(f['kind'], f['subject'], f.get('counterpart')) for f in out] == [('VAGUE_TERM', 'GAS-2', None),
                                                                              ('REDUNDANCY', 'GAS-2', 'GAS-6')]
    assert out[0]['text'] == '"settle" is not checkable', 'the first of a repeated finding is kept'


@pytest.mark.parametrize('raw, module, message', [
    ('not json', contradiction, 'not JSON'),
    (json.dumps({'clauses': []}), contradiction, 'no {"findings"'),
    (answer(finding('VAGUE_TERM', 'GAS-2')), contradiction, 'does not report'),
    (answer(finding('CONTRADICTION', 'GAS-2', 'GAS-6')), quality, 'does not report'),
    (answer(finding('GAP', 'GAS-2')), quality, 'does not report'),
    (answer(dict(finding('CONTRADICTION', 'GAS-2', 'GAS-6'), witness='x')), contradiction, 'unknown field'),
    (answer(finding('CONTRADICTION', 'GAS-2', 'GAS-6', text=' ')), contradiction, 'no text'),
    (answer(finding('CONTRADICTION', 'GAS-99', 'GAS-6')), contradiction, 'not one of the agreed NEEDs'),
    (answer(finding('CONTRADICTION', 'GAS-2')), contradiction, 'names no other agreed NEED'),
    (answer(finding('CONTRADICTION', 'GAS-2', 'GAS-2')), contradiction, 'names no other agreed NEED'),
    (answer(finding('REDUNDANCY', 'GAS-2')), quality, 'names no other agreed NEED'),
    (answer(finding('VAGUE_TERM', 'GAS-2', 'GAS-99')), quality, 'not another agreed NEED'),
])
def test_check_refuses(raw, module, message):
    with pytest.raises(ValueError) as e:
        cv.findings_of(raw, NEEDS, module.KINDS, module.PAIR_KINDS)
    assert message in str(e.value)


def test_conflict_key():
    assert cv.conflict_key('CONTRADICTION', 'GAS-6', 'GAS-2', ('CONTRADICTION',)) == 'CONTRADICTION|GAS-2|GAS-6'
    assert cv.conflict_key('VAGUE_TERM', 'GAS-6', None, ('REDUNDANCY',)) == 'VAGUE_TERM|GAS-6'
    assert cv.conflict_key('VAGUE_TERM', 'GAS-6', 'GAS-2', ('REDUNDANCY',)) == 'VAGUE_TERM|GAS-6'


# ==================== FEASIBILITY (plan 047, Phase 11) ====================

WITNESS = ('One publisher per station keeps the newest price and resends it until acknowledged: GAS-2 holds by resending '
           'the newest; GAS-6 is met by never replacing the first; GAS-7 by coalescing; GAS-9 by default.')


def test_feasibility_prompt_tail_and_verdicts():
    prompt = feasibility.compose(NEEDS)
    lines = prompt.split('\n')
    assert lines[-1].startswith('Print nothing')
    assert lines[-2] == feasibility.ANSWER_SHAPE
    assert 'mh_cc_store_result' in lines[-4] or 'mh_cc_store_result' in lines[-3]
    for v in feasibility.VERDICTS:
        assert '- ' + v + ':' in prompt, v
    assert 'MINIMAL set' in prompt
    assert 'names EVERY agreed NEED' in prompt
    assert 'Optimality is not a criterion' in prompt
    assert prompt.index('NEED GAS-9') < prompt.index('mh_cc_store_result'), 'the instruction is LAST'


def test_feasibility_infeasible_canonical():
    raw = json.dumps({'verdict': 'INFEASIBLE', 'needReqIds': [' GAS-6', 'GAS-2'], 'reason': ' keep first vs latest ',
                      'witness': None, 'openChoices': []})
    assert feasibility.verdict_of(raw, NEEDS) == {'verdict': 'INFEASIBLE', 'needReqIds': ['GAS-6', 'GAS-2'],
                                                  'reason': 'keep first vs latest'}


def test_feasibility_underdetermined_and_determined_canonical():
    out = feasibility.verdict_of(json.dumps({'verdict': 'UNDERDETERMINED', 'witness': WITNESS,
                                             'openChoices': ['the resend interval']}), NEEDS)
    assert out == {'verdict': 'UNDERDETERMINED', 'witness': WITNESS, 'openChoices': ['the resend interval']}
    out = feasibility.verdict_of(json.dumps({'verdict': 'DETERMINED', 'witness': WITNESS, 'needReqIds': []}), NEEDS)
    assert out == {'verdict': 'DETERMINED', 'witness': WITNESS}


def test_feasibility_witness_names_need_by_reqid_not_by_prefix():
    assert feasibility.names('meets GAS-2 and GAS-21', 'GAS-2')
    assert not feasibility.names('meets GAS-21 only', 'GAS-2')


@pytest.mark.parametrize('answer_object, message', [
    ({'verdict': 'MAYBE', 'witness': WITNESS}, 'unknown verdict'),
    ({'verdict': 'DETERMINED', 'witness': WITNESS, 'design': 'x'}, 'unknown field'),
    ({'verdict': 'INFEASIBLE', 'needReqIds': [], 'reason': 'r'}, 'at least one NEED'),
    ({'verdict': 'INFEASIBLE', 'reason': 'r'}, 'at least one NEED'),
    ({'verdict': 'INFEASIBLE', 'needReqIds': ['GAS-99'], 'reason': 'r'}, 'not one of the agreed NEEDs'),
    ({'verdict': 'INFEASIBLE', 'needReqIds': ['GAS-2', 'GAS-2'], 'reason': 'r'}, 'twice'),
    ({'verdict': 'INFEASIBLE', 'needReqIds': ['GAS-2'], 'reason': ' '}, 'reason'),
    ({'verdict': 'DETERMINED'}, 'witness design'),
    ({'verdict': 'DETERMINED', 'witness': WITNESS.replace('GAS-9', 'the last')}, 'does not name NEED GAS-9'),
    ({'verdict': 'DETERMINED', 'witness': WITNESS + 'x' * 2000}, 'at most 2000'),
    ({'verdict': 'UNDERDETERMINED', 'witness': WITNESS}, 'leave open'),
    ({'verdict': 'UNDERDETERMINED', 'witness': WITNESS, 'openChoices': [' ']}, 'leave open'),
])
def test_feasibility_check_refuses(answer_object, message):
    with pytest.raises(ValueError) as e:
        feasibility.verdict_of(json.dumps(answer_object), NEEDS)
    assert message in str(e.value)


def test_feasibility_check_refuses_a_non_object():
    with pytest.raises(ValueError) as e:
        feasibility.verdict_of('["DETERMINED"]', NEEDS)
    assert 'no {"verdict"' in str(e.value)


# ==================== BACKTRACE (plan 047, Phase 17) ====================

BT_CONTEXT = {
    'snapshotId': 249,
    'needs': [
        {'reqId': 'GAS-2', 'revision': 2, 'title': 'Settle within a minute',
         'statement': 'Each station must settle on the latest price,\nand the pricing team knows within one minute.',
         'kind': 'OBLIGATION'},
        {'reqId': 'GAS-7', 'revision': 1, 'title': 'Costs', 'statement': 'Sending has a cost.', 'kind': 'COST_OBJECTIVE'},
    ],
    'subjects': [
        {'reqId': 'GAS-10', 'liveReqId': 'GAS-10', 'held': False, 'sectionReqId': None, 'title': 'Latest price',
         'statement': 'The service shall make every station display the latest price.',
         'rationale': 'need: GAS-2 r1\nrestates GAS-2', 'citations': ['GAS-2 r1'],
         'superseded': [{'needReqId': 'GAS-2', 'revision': 1, 'title': 'Settle',
                         'statement': 'Each station must settle on the latest price.'}],
         'tracedFrom': ['GAS-2']},
        {'reqId': 'GAS-11', 'liveReqId': 'GAS-14', 'held': False, 'sectionReqId': None, 'title': 'Resend spacing',
         'statement': 'The service shall send a price at most once every 60 seconds.', 'rationale': '',
         'citations': [], 'superseded': [], 'tracedFrom': []},
        {'reqId': 'GAS-12', 'liveReqId': 'GAS-12', 'held': False, 'sectionReqId': None, 'title': 'Old cite',
         'statement': 'The service shall log every send.', 'rationale': 'need: GAS-3 r1', 'citations': ['GAS-3 r1'],
         'superseded': [{'needReqId': 'GAS-3', 'revision': 1, 'title': None, 'statement': None}], 'tracedFrom': []},
        {'reqId': 'GAS-20', 'liveReqId': 'GAS-20', 'held': True, 'sectionReqId': 'GAS-19', 'title': 'Periodic resend',
         'statement': 'The service shall resend the latest price to every station every 10 seconds.', 'rationale': '',
         'citations': [], 'superseded': [], 'tracedFrom': ['GAS-7']},
    ],
}
BT_CHUNK = ['GAS-10', 'GAS-11', 'GAS-20']


def bt_verdict(subject, verdict, text='why', **fields):
    v = {'subject': subject, 'verdict': verdict, 'text': text}
    v.update(fields)
    return v


def bt_answer(*verdicts):
    return json.dumps({'verdicts': list(verdicts)})


def test_backtrace_prompt_ends_with_the_answer_instruction():
    lines = backtrace.compose(BT_CONTEXT, BT_CHUNK).split('\n')
    assert lines[-1] == cv.ANSWER_TAIL.replace('the findings', 'the verdicts')
    assert lines[-2] == backtrace.ANSWER_SHAPE
    assert lines[-4].startswith('Answer by calling the mh_cc_store_result tool exactly once')
    assert 'Print nothing' in lines[-1]


def test_backtrace_prompt_lists_the_needs_and_the_chunk_only():
    prompt = backtrace.compose(BT_CONTEXT, BT_CHUNK)
    assert 'NEED GAS-2 (revision 2, OBLIGATION): Settle within a minute' in prompt
    assert '  and the pricing team knows within one minute.' in prompt, 'a multi-line statement keeps its lines'
    assert 'NEED GAS-7 (revision 1, COST_OBJECTIVE): Costs' in prompt
    assert 'Owned requirement GAS-10 (top-level - JUSTIFIED, OVER_REACH, CONTRADICTS_NEED or RESTS_ON_SUPERSEDED):' in prompt
    assert 'Owned requirement GAS-11 (now GAS-14)' in prompt, 'a lineage read at its live row says so'
    assert 'Held requirement GAS-20 (imposed through section GAS-19 - JUSTIFIED, CONTRADICTS_NEED or UNNEEDED):' in prompt
    assert '    Rationale: need: GAS-2 r1 | restates GAS-2' in prompt
    assert '    Cites GAS-2 r1, no longer in force - it read then: Settle: Each station must settle on the latest price.' in prompt
    assert '    Traced from: no NEED' in prompt
    assert '    Traced from: GAS-7' in prompt
    assert 'GAS-12' not in prompt, 'a subject of another chunk is not listed'
    assert prompt.index('Held requirement GAS-20') < prompt.index('mh_cc_store_result'), 'the instruction is LAST'
    for rule in ('OVER_REACH (owned requirements only)', 'UNNEEDED (held requirements only)',
                 'a fixed bound on that cost', 'it obliges nothing', 'A NEED without a kind is an OBLIGATION.'):
        assert rule in prompt, rule


def test_backtrace_prompt_superseded_revision_off_the_line():
    prompt = backtrace.compose(BT_CONTEXT, ['GAS-12'])
    assert "    Cites GAS-3 r1, no longer in force - its text is not on the project's line" in prompt


def test_backtrace_verdict_naming_the_live_row_of_its_subject():
    # plan 047 Phase 28 (A run 3, #54 BACKTRACE #358, #361, #363): after a REDEFINITION the prompt lists a CHANGED
    # requirement as "GAS-11 (now GAS-14)", and CC answered with the live reqId as the subject
    # plan 050 Phase 9 (fixture change): an OVER_REACH names its counterexample, or it is dropped
    answer = bt_answer(bt_verdict('GAS-10', 'OVER_REACH', counterexample='c'), bt_verdict('GAS-14', 'OVER_REACH', counterexample='c'),
                       bt_verdict('GAS-20', 'UNNEEDED'))
    assert [v['subject'] for v in backtrace.verdicts_of(answer, BT_CONTEXT, BT_CHUNK)['verdicts']] == \
        ['GAS-10', 'GAS-11', 'GAS-20'], 'the live row names its subject'
    with pytest.raises(ValueError) as e:
        backtrace.verdicts_of(bt_answer(bt_verdict('GAS-11', 'OVER_REACH'), bt_verdict('GAS-14', 'OVER_REACH'),
                                        bt_verdict('GAS-10', 'OVER_REACH'), bt_verdict('GAS-20', 'UNNEEDED')),
                              BT_CONTEXT, BT_CHUNK)
    assert 'names GAS-11 a second time' in str(e.value), 'the subject and its live row are one subject'


def test_backtrace_verdicts_canonical_in_chunk_order():
    raw = '```json\n' + bt_answer(
        bt_verdict('GAS-20', 'UNNEEDED', 'no NEED asks for periodic resends', needReqIds=[], needReqId=None),
        bt_verdict(' GAS-10 ', 'RESTS_ON_SUPERSEDED', ' rests on "settle" ', needReqId='GAS-2'),
        bt_verdict('GAS-11', 'JUSTIFIED', 'GAS-7 weighs sends', needReqIds=['GAS-7', 'GAS-2'])) + '\n```'
    assert backtrace.verdicts_of(raw, BT_CONTEXT, BT_CHUNK) == {'verdicts': [
        {'subject': 'GAS-10', 'verdict': 'RESTS_ON_SUPERSEDED', 'text': 'rests on "settle"', 'needReqId': 'GAS-2'},
        {'subject': 'GAS-11', 'verdict': 'JUSTIFIED', 'text': 'GAS-7 weighs sends', 'needReqIds': ['GAS-7', 'GAS-2']},
        {'subject': 'GAS-20', 'verdict': 'UNNEEDED', 'text': 'no NEED asks for periodic resends'},
    ]}
    other = backtrace.verdicts_of(bt_answer(
        bt_verdict('GAS-10', 'CONTRADICTS_NEED', 'a stale price', needReqId='GAS-2'),
        bt_verdict('GAS-11', 'OVER_REACH', '"at most once every 60 seconds"', counterexample='two prices 10 s apart'),
        bt_verdict('GAS-20', 'CONTRADICTS_NEED', 'resends cost', needReqId='GAS-7')), BT_CONTEXT, BT_CHUNK)
    assert [v['verdict'] for v in other['verdicts']] == ['CONTRADICTS_NEED', 'OVER_REACH', 'CONTRADICTS_NEED']
    assert 'needReqId' not in other['verdicts'][1]


@pytest.mark.parametrize('verdicts, message', [
    ([bt_verdict('GAS-10', 'OVER_REACH'), bt_verdict('GAS-11', 'OVER_REACH')], 'no verdict on GAS-20'),
    ([bt_verdict('GAS-12', 'OVER_REACH')], 'not a requirement of this chunk'),
    ([bt_verdict('GAS-10', 'OVER_REACH'), bt_verdict('GAS-10', 'OVER_REACH')], 'a second time'),
    ([bt_verdict('GAS-10', 'MAYBE')], 'unknown verdict'),
    ([bt_verdict('GAS-10', 'OVER_REACH', text=' ')], 'no text'),
    ([bt_verdict('GAS-10', 'OVER_REACH', kind='x')], 'unknown field'),
    ([bt_verdict('GAS-10', 'JUSTIFIED')], 'names no NEED'),
    ([bt_verdict('GAS-10', 'JUSTIFIED', needReqIds=['GAS-9'])], 'not one of the agreed NEEDs'),
    ([bt_verdict('GAS-10', 'JUSTIFIED', needReqIds=['GAS-2', 'GAS-2'])], 'twice'),
    ([bt_verdict('GAS-10', 'JUSTIFIED', needReqIds='GAS-2')], 'not a list'),
    ([bt_verdict('GAS-10', 'OVER_REACH', needReqIds=['GAS-2'])], 'only JUSTIFIED does'),
    ([bt_verdict('GAS-10', 'OVER_REACH', needReqId='GAS-2')], 'only CONTRADICTS_NEED and RESTS_ON_SUPERSEDED do'),
    ([bt_verdict('GAS-10', 'CONTRADICTS_NEED')], 'names no agreed NEED'),
    ([bt_verdict('GAS-10', 'CONTRADICTS_NEED', needReqId='GAS-3')], 'names no agreed NEED'),
    ([bt_verdict('GAS-10', 'CONTRADICTS_NEED', needReqId=7)], 'not a reqId'),
    ([bt_verdict('GAS-11', 'RESTS_ON_SUPERSEDED', needReqId='GAS-2')], 'no NEED it cites at a revision no longer in force'),
    ([bt_verdict('GAS-10', 'RESTS_ON_SUPERSEDED', needReqId='GAS-7')], 'no NEED it cites at a revision no longer in force'),
    ([bt_verdict('GAS-10', 'UNNEEDED')], "a held requirement's verdict only"),
    ([bt_verdict('GAS-20', 'OVER_REACH')], "an owned requirement's verdict only"),
])
def test_backtrace_check_refuses(verdicts, message):
    with pytest.raises(ValueError) as e:
        backtrace.verdicts_of(bt_answer(*verdicts), BT_CONTEXT, BT_CHUNK)
    assert message in str(e.value)


def test_backtrace_an_over_reach_and_its_counterexample():
    # plan 050 Phase 9 (decision 11) - characterization test: Green-1 pinned v7 (an OVER_REACH with no counterexample was in
    # the canonical answer); an OVER_REACH ("not necessary") needs a NEED-compliant situation the requirement forbids - the
    # check drops one without it; the subject still counts as answered
    out = backtrace.verdicts_of(bt_answer(bt_verdict('GAS-10', 'OVER_REACH', '"every station"'), bt_verdict('GAS-11', 'JUSTIFIED',
                                                    needReqIds=['GAS-2']), bt_verdict('GAS-20', 'UNNEEDED')), BT_CONTEXT, BT_CHUNK)
    assert [v['subject'] for v in out['verdicts']] == ['GAS-11', 'GAS-20'], 'the OVER_REACH without a counterexample is dropped'
    kept = backtrace.verdicts_of(bt_answer(
        bt_verdict('GAS-10', 'OVER_REACH', '"every station"', direction=' each station that is sent a price ',
                   counterexample=' a station that is never sent a price '),
        bt_verdict('GAS-11', 'JUSTIFIED', needReqIds=['GAS-2']),
        bt_verdict('GAS-20', 'CONTRADICTS_NEED', 'resends cost', needReqId='GAS-7', direction='resend on change only')),
        BT_CONTEXT, BT_CHUNK)['verdicts']
    assert kept[0] == {'subject': 'GAS-10', 'verdict': 'OVER_REACH', 'text': '"every station"',
                       'direction': 'each station that is sent a price', 'counterexample': 'a station that is never sent a price'}
    assert kept[2]['direction'] == 'resend on change only' and 'counterexample' not in kept[2]


def test_backtrace_check_refuses_a_non_object():
    with pytest.raises(ValueError) as e:
        backtrace.verdicts_of(json.dumps({'findings': []}), BT_CONTEXT, BT_CHUNK)
    assert 'no {"verdicts"' in str(e.value)


def test_backtrace_justified_without_text():
    # development run 244 (project #48): CC answered every JUSTIFIED with needReqIds only - the prompt asks for "only the
    # fields its verdict uses", and a JUSTIFIED verdict stores nothing
    raw = bt_answer({'subject': 'GAS-10', 'verdict': 'JUSTIFIED', 'needReqIds': ['GAS-2']},
                    bt_verdict('GAS-11', 'OVER_REACH', '"at most once every 60 seconds"', counterexample='two prices 10 s apart'),
                    {'subject': 'GAS-20', 'verdict': 'JUSTIFIED', 'needReqIds': ['GAS-7'], 'text': None})
    assert backtrace.verdicts_of(raw, BT_CONTEXT, BT_CHUNK) == {'verdicts': [
        {'subject': 'GAS-10', 'verdict': 'JUSTIFIED', 'needReqIds': ['GAS-2']},
        {'subject': 'GAS-11', 'verdict': 'OVER_REACH', 'text': '"at most once every 60 seconds"', 'counterexample': 'two prices 10 s apart'},
        {'subject': 'GAS-20', 'verdict': 'JUSTIFIED', 'needReqIds': ['GAS-7']},
    ]}, 'a JUSTIFIED verdict needs no text; every other verdict still does'


@pytest.mark.parametrize('raw, message', [
    ('', 'the chunk names no subject'),
    ('GAS-10\nGAS-99', "'GAS-99', which is not a subject"),
    ('GAS-10\n\nGAS-10', 'twice'),
])
def test_backtrace_chunk_of_refuses(raw, message):
    with pytest.raises(ValueError) as e:
        backtrace.chunk_of(raw, BT_CONTEXT)
    assert message in str(e.value)


def test_backtrace_context_of():
    assert backtrace.chunk_of(' GAS-10 \n\nGAS-20\n', BT_CONTEXT) == ['GAS-10', 'GAS-20'], 'blank lines are skipped'
    assert backtrace.context_of(json.dumps(BT_CONTEXT))['snapshotId'] == 249
    for raw, message in (('not json', 'not JSON'), ('{"needs": []}', 'no needs and subjects'),
                         ('{"needs": [], "subjects": [{"held": true}]}', 'with no reqId')):
        with pytest.raises(ValueError) as e:
            backtrace.context_of(raw)
        assert message in str(e.value)
    assert backtrace.CHUNK_SIZE == 40
