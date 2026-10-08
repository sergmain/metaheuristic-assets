# The NEED wording's prompt and check (plan 045, Phase 8): nrvv_wording.

import json

import pytest

import nrvv_wording as nw

SCENARIO = ('Gas stations receive every new price from the pricing service. Only eventual correctness matters, where '
            'each station must settle on the latest price. Stations report what they hold.')

AGREED = [{'reqId': 'GAS-1', 'revision': 1, 'title': 'Gas stations settle on the latest price', 'statement': SCENARIO,
           'parentReqId': None},
          {'reqId': 'GAS-2', 'revision': 3, 'title': 'Stations show the price per litre',
           'statement': 'The pricing team needs every station to show the price per litre.', 'parentReqId': None}]

PROPOSAL = {'id': 7, 'ref': 'P-7', 'title': 'Stations acknowledge a new price within one minute',
            'statement': 'The pricing team needs to know within one minute that a station holds a new price.',
            'parentNeedReqId': None,
            'source': {'stakeholder': 'pricing team', 'text': 'latency for ack order is no more than 1 minute',
                       'date': None},
            'digest': 'ab' * 32}

INSTRUCTION = 'keep eventual settling; add that the pricing team knows within one minute that a station holds a new price'
REQUEST = {'targetNeedReqId': 'GAS-1', 'instruction': INSTRUCTION}


# ==================== inputs ====================

def test_request_of_reads_target_and_instruction():
    assert nw.request_of(json.dumps(REQUEST)) == REQUEST


@pytest.mark.parametrize('raw', ['', 'not json', '[]', json.dumps({'targetNeedReqId': 'GAS-1', 'instruction': ' '}),
                                 json.dumps({'instruction': 'x'})])
def test_request_of_refuses(raw):
    with pytest.raises(ValueError):
        nw.request_of(raw)


def test_target_of_finds_the_agreed_need():
    assert nw.target_of(REQUEST, AGREED)['title'] == 'Gas stations settle on the latest price'


def test_target_of_refuses_a_need_not_at_the_snapshot():
    with pytest.raises(ValueError, match='not one of the agreed NEEDs'):
        nw.target_of({'targetNeedReqId': 'GAS-9', 'instruction': 'x'}, AGREED)


# ==================== prompt ====================

def test_compose_carries_target_proposal_instruction_and_the_other_needs():
    prompt = nw.compose(PROPOSAL, REQUEST, AGREED)
    assert 'GAS-1 (revision 1):' in prompt
    assert SCENARIO in prompt
    assert PROPOSAL['statement'] in prompt
    assert 'latency for ack order is no more than 1 minute' in prompt
    assert INSTRUCTION in prompt
    assert 'The other agreed NEEDs:' in prompt
    assert 'GAS-2 (revision 3): Stations show the price per litre' in prompt
    assert '{"title": "<the amended title>", "statement": "<the whole amended statement>"}' in prompt
    assert 'The subject is the stakeholder, never a system' in prompt
    # the target is not listed again among the others
    assert prompt.count(SCENARIO) == 1


def test_compose_with_the_target_alone():
    assert 'The project has no other agreed NEED.' in nw.compose(PROPOSAL, REQUEST, AGREED[:1])


def test_compose_refuses_a_target_not_at_the_snapshot():
    with pytest.raises(ValueError):
        nw.compose(PROPOSAL, {'targetNeedReqId': 'GAS-9', 'instruction': 'x'}, AGREED)


# ==================== check ====================

def test_wording_of_canonical_form():
    answer = nw.wording_of(json.dumps({'title': '  Gas stations settle on the latest price ',
                                       'statement': '\nThe pricing team needs ... within one minute.\n'}))
    assert answer == {'title': 'Gas stations settle on the latest price',
                      'statement': 'The pricing team needs ... within one minute.'}


def test_wording_of_unwraps_one_fence_and_keeps_a_multi_line_statement():
    answer = nw.wording_of('```json\n{"title": "T", "statement": "one.\\ntwo."}\n```')
    assert answer == {'title': 'T', 'statement': 'one.\ntwo.'}


def test_wording_of_title_at_the_limit():
    assert len(nw.wording_of(json.dumps({'title': 't' * 250, 'statement': 'S'}))['title']) == 250


@pytest.mark.parametrize('answer, message', [
    ('not json', 'not JSON'),
    ('["T", "S"]', 'no {"title", "statement"} object'),
    ('{"title": "T", "statement": "S", "recommendation": "accept"}', 'unknown field'),
    ('{"statement": "S"}', 'no title'),
    ('{"title": " ", "statement": "S"}', 'no title'),
    ('{"title": 5, "statement": "S"}', 'no title'),
    ('{"title": "T"}', 'no statement'),
    ('{"title": "T", "statement": "  "}', 'no statement'),
    ('{"title": "one\\ntwo", "statement": "S"}', 'not one line'),
    (json.dumps({'title': 't' * 251, 'statement': 'S'}), 'longer than 250'),
])
def test_wording_of_refuses(answer, message):
    with pytest.raises(ValueError, match=message):
        nw.wording_of(answer)
