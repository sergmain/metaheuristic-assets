# The NEED assessment's prompt and check (plan 045, Phase 7): nrvv_assessment.

import json

import pytest

import nrvv_assessment as na

SCENARIO = ('Gas stations receive every new price from the pricing service. Only eventual correctness matters, where '
            'each station must settle on the latest price. Stations report what they hold.')

AGREED = [{'reqId': 'GAS-1', 'revision': 1, 'title': 'Gas stations settle on the latest price', 'statement': SCENARIO,
           'parentReqId': None}]
AGREED_JSON = json.dumps(AGREED)

PROPOSAL = {'id': 7, 'ref': 'P-7', 'title': 'Stations acknowledge a new price within one minute',
            'statement': 'The pricing team needs to know within one minute that a station holds a new price.',
            'parentNeedReqId': None,
            'source': {'stakeholder': 'pricing team', 'text': 'latency for ack order is no more than 1 minute',
                       'date': None},
            'digest': 'ab' * 32}
PROPOSAL_JSON = json.dumps(PROPOSAL)


# ==================== inputs ====================

def test_proposal_of_reads_the_frozen_proposal():
    assert na.proposal_of(PROPOSAL_JSON)['ref'] == 'P-7'


@pytest.mark.parametrize('raw', ['', 'not json', '[]', json.dumps({'title': 'T', 'statement': ' '})])
def test_proposal_of_refuses(raw):
    with pytest.raises(ValueError):
        na.proposal_of(raw)


def test_agreed_needs_of_empty_and_list():
    assert na.agreed_needs_of('[]') == []
    assert na.agreed_needs_of(AGREED_JSON)[0]['reqId'] == 'GAS-1'
    with pytest.raises(ValueError):
        na.agreed_needs_of('[{"title": "no reqId"}]')


# ==================== prompt ====================

def test_compose_carries_the_proposal_and_every_agreed_need_verbatim():
    prompt = na.compose(PROPOSAL, AGREED)
    assert 'P-7' in prompt
    assert PROPOSAL['statement'] in prompt
    assert 'latency for ack order is no more than 1 minute' in prompt
    assert 'GAS-1 (revision 1)' in prompt
    assert SCENARIO in prompt
    assert '{"findings": [' in prompt
    assert 'Never recommend an outcome' in prompt


def test_compose_without_agreed_needs():
    assert 'The project has no agreed NEED yet.' in na.compose(PROPOSAL, [])


# ==================== check ====================

def test_findings_of_canonical_form():
    answer = na.findings_of(json.dumps({'findings': [
        {'kind': 'CONTRADICTION', 'counterpart': 'GAS-1', 'text': ' one minute vs eventual '},
        {'kind': 'VAGUE_TERM', 'counterpart': None, 'text': 'new price'}]}), AGREED)
    assert answer == {'findings': [{'kind': 'CONTRADICTION', 'counterpart': 'GAS-1', 'text': 'one minute vs eventual'},
                                   {'kind': 'VAGUE_TERM', 'text': 'new price'}]}


def test_findings_of_unwraps_one_fence_and_accepts_no_finding():
    assert na.findings_of('```json\n{"findings": []}\n```', AGREED) == {'findings': []}


@pytest.mark.parametrize('answer, message', [
    ('not json', 'not JSON'),
    ('{"findings": [], "outcome": "ACCEPT"}', 'no {"findings"'),
    ('{"findings": [{"kind": "OPINION", "text": "x"}]}', 'unknown kind'),
    ('{"findings": [{"kind": "GAP", "text": "x"}]}', 'unknown kind'),
    ('{"findings": [{"kind": "VAGUE_TERM", "text": "x", "outcome": "REJECT"}]}', 'unknown field'),
    ('{"findings": [{"kind": "VAGUE_TERM", "text": " "}]}', 'no text'),
    ('{"findings": [{"kind": "CONTRADICTION", "text": "x"}]}', 'names no counterpart'),
    ('{"findings": [{"kind": "REDUNDANCY", "counterpart": "GAS-9", "text": "x"}]}', 'not one of the agreed NEEDs'),
])
def test_findings_of_refuses(answer, message):
    with pytest.raises(ValueError, match=message):
        na.findings_of(answer, AGREED)
