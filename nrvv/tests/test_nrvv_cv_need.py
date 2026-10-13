# The NEED checks of NRVV v5 (plan 047, Phase 10): the CONTRADICTION and QUALITY prompts - their tails and what they
# list - and every refusal of the shared check, the mirrored pair stored once.

import json

import pytest

import nrvv_cv_need as cv
import nrvv_cv_need_contradiction as contradiction
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
