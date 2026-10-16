# The NEED check EXPECTATION (plan 048, Phase 5): the prompt - the chunk's NEEDs with their clauses, the answer
# instruction last - and every refusal of the check, the verdicts in chunk order.

import json

import pytest

import nrvv_cv_need_expectation as expectation

NEEDS = [
    {'reqId': 'GAS-2', 'revision': 1, 'title': 'Settle on the latest price',
     'statement': 'The pricing team needs each station to settle on the latest price.', 'parentReqId': None,
     'kind': 'OBLIGATION',
     'clause': 'Only eventual correctness matters, where each station must settle on the latest price.'},
    {'reqId': 'GAS-3', 'revision': 1, 'title': 'Out-of-order arrival',
     'statement': 'Sends can arrive at a station out of order.', 'parentReqId': None, 'kind': 'ENVIRONMENT_FACT',
     'clause': 'Your sends can arrive at the station out of order,\nbut all acknowledgements come back in order.'},
    {'reqId': 'GAS-7', 'revision': 1, 'title': 'Sending costs', 'statement': 'Sending has a cost.', 'parentReqId': None,
     'kind': 'COST_OBJECTIVE', 'clause': 'Sending has a COST -> don\'t spam, and avoid unnecessary updates.'},
    {'reqId': 'GAS-9', 'revision': 1, 'title': 'A NEED written by a person', 'statement': 'No clause.',
     'parentReqId': None, 'kind': 'OBLIGATION', 'clause': None},
    {'reqId': 'GAS-10', 'revision': 1, 'title': 'A v4 NEED', 'statement': 'No kind, no clause field.', 'parentReqId': None},
]

CHUNK = ['GAS-2', 'GAS-3', 'GAS-7']


def verdict(subject, kind, text='why'):
    v = {'subject': subject, 'verdict': kind}
    if text is not None:
        v['text'] = text
    return v


def answer(*verdicts):
    return json.dumps({'verdicts': list(verdicts)})


# ==================== subjects and chunks ====================

def test_subjects_are_the_needs_with_a_clause_in_order():
    assert expectation.subjects_of(NEEDS) == ['GAS-2', 'GAS-3', 'GAS-7']


def test_a_blank_clause_is_no_clause():
    assert expectation.subjects_of([{'reqId': 'GAS-1', 'clause': '  \n '}]) == []


def test_chunk_of_reads_one_reqid_per_line():
    assert expectation.chunk_of('GAS-3\n\nGAS-2\n', NEEDS) == ['GAS-3', 'GAS-2']


@pytest.mark.parametrize('raw, message', [
    ('', 'names no subject'),
    ('GAS-9', "'GAS-9', which is not an agreed NEED with a clause"),
    ('GAS-10', "'GAS-10', which is not an agreed NEED with a clause"),
    ('GAS-404', "'GAS-404', which is not an agreed NEED with a clause"),
    ('GAS-2\nGAS-2', 'names a subject twice'),
])
def test_chunk_of_refuses(raw, message):
    with pytest.raises(ValueError, match=message):
        expectation.chunk_of(raw, NEEDS)


# ==================== the prompt ====================

def test_prompt_ends_with_the_answer_instruction():
    lines = expectation.compose(NEEDS, CHUNK).split('\n')
    assert lines[-2] == expectation.ANSWER_SHAPE
    assert lines[-1].startswith('Print nothing - neither the verdicts nor any explanation')
    assert lines[-4].startswith('Answer by calling the mh_cc_store_result tool exactly once')


def test_prompt_lists_each_need_of_the_chunk_with_its_clause_quoted_line_by_line():
    prompt = expectation.compose(NEEDS, CHUNK)
    assert 'NEED GAS-2 (OBLIGATION): Settle on the latest price' in prompt
    assert '    > Only eventual correctness matters, where each station must settle on the latest price.' in prompt
    assert 'NEED GAS-3 (ENVIRONMENT_FACT): Out-of-order arrival' in prompt
    assert '    > Your sends can arrive at the station out of order,\n    > but all acknowledgements come back in order.' in prompt
    assert 'NEED GAS-7 (COST_OBJECTIVE): Sending costs' in prompt


def test_prompt_lists_the_chunk_only():
    prompt = expectation.compose(NEEDS, ['GAS-3'])
    assert 'NEED GAS-3 ' in prompt
    assert 'NEED GAS-2 ' not in prompt
    assert 'NEED GAS-7 ' not in prompt
    assert 'NEED GAS-9 ' not in prompt


def test_prompt_names_the_four_verdicts_and_their_order_of_precedence():
    prompt = expectation.compose(NEEDS, CHUNK)
    for v in expectation.VERDICTS:
        assert '- ' + v + ':' in prompt
    assert 'CONTRADICTS_EXPECTATION,\n  OVER_STATES, UNDER_STATES.' in prompt
    assert 'Judge each NEED against ITS OWN clause only' in prompt


# ==================== the check ====================

def test_verdicts_canonical_in_chunk_order():
    raw = answer(verdict('GAS-7', 'UNDER_STATES', ' drops "avoid unnecessary updates" '),
                 verdict('GAS-2', 'FAITHFUL', None),
                 verdict('GAS-3', 'OVER_STATES', '"the system shall reorder"'))
    assert expectation.verdicts_of(raw, CHUNK) == {'verdicts': [
        {'subject': 'GAS-2', 'verdict': 'FAITHFUL'},
        {'subject': 'GAS-3', 'verdict': 'OVER_STATES', 'text': '"the system shall reorder"'},
        {'subject': 'GAS-7', 'verdict': 'UNDER_STATES', 'text': 'drops "avoid unnecessary updates"'},
    ]}


def test_faithful_keeps_a_text_given_and_a_fence_is_unwrapped():
    raw = '```json\n' + answer(verdict('GAS-2', 'FAITHFUL', 'restates it'),
                               verdict('GAS-3', 'CONTRADICTS_EXPECTATION', 'in order vs out of order'),
                               verdict('GAS-7', 'FAITHFUL', '')) + '\n```'
    assert expectation.verdicts_of(raw, CHUNK) == {'verdicts': [
        {'subject': 'GAS-2', 'verdict': 'FAITHFUL', 'text': 'restates it'},
        {'subject': 'GAS-3', 'verdict': 'CONTRADICTS_EXPECTATION', 'text': 'in order vs out of order'},
        {'subject': 'GAS-7', 'verdict': 'FAITHFUL'},
    ]}


@pytest.mark.parametrize('verdicts, message', [
    ([verdict('GAS-2', 'FAITHFUL'), verdict('GAS-3', 'FAITHFUL'), verdict('GAS-7', 'WRONG')], "unknown verdict 'WRONG'"),
    ([verdict('GAS-2', 'FAITHFUL'), verdict('GAS-3', 'OVER_STATES', ' '), verdict('GAS-7', 'FAITHFUL')], r'\(GAS-3\) has no text'),
    ([verdict('GAS-2', 'FAITHFUL'), verdict('GAS-3', 'UNDER_STATES', None), verdict('GAS-7', 'FAITHFUL')], r'\(GAS-3\) has no text'),
    ([verdict('GAS-2', 'FAITHFUL'), verdict('GAS-3', 'OVER_STATES', 7), verdict('GAS-7', 'FAITHFUL')], 'not a string'),
    ([verdict('GAS-2', 'FAITHFUL'), verdict('GAS-9', 'FAITHFUL')], "'GAS-9', which is not a NEED of this chunk"),
    ([verdict('GAS-2', 'FAITHFUL'), verdict('GAS-2', 'FAITHFUL')], 'names GAS-2 a second time'),
    ([verdict('GAS-2', 'FAITHFUL'), verdict('GAS-3', 'FAITHFUL')], 'CC gave no verdict on GAS-7'),
    ([dict(verdict('GAS-2', 'FAITHFUL'), needReqId='GAS-3')], "unknown field 'needReqId'"),
    (['GAS-2'], 'is not an object'),
])
def test_check_refuses(verdicts, message):
    with pytest.raises(ValueError, match=message):
        expectation.verdicts_of(answer(*verdicts), CHUNK)


@pytest.mark.parametrize('raw', ['not json', json.dumps([]), json.dumps({'findings': []}),
                                 json.dumps({'verdicts': [], 'note': 'x'})])
def test_check_refuses_a_non_answer(raw):
    with pytest.raises(ValueError):
        expectation.verdicts_of(raw, CHUNK)
