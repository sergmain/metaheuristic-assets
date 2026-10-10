# Allocation proposals' prompt and check (plan 045, Phase 25): nrvv_allocation_proposal.

import json

import pytest

import nrvv_allocation_proposal as ap

CONTEXT = {
    'snapshotId': 77,
    'elements': [
        {'code': 'ack-tracker', 'name': 'Acknowledgement tracker', 'description': 'keeps\nwhich station holds which price'},
        {'code': 'publisher', 'name': 'Price publisher', 'description': None},
    ],
    'topLevel': [
        {'reqId': 'GAS-3', 'liveReqId': 'GAS-3', 'title': 'Settle on the latest price',
         'statement': 'The service shall make every station display the latest price.', 'designItems': ['GAS-7']},
        {'reqId': 'GAS-4', 'liveReqId': 'GAS-9', 'title': 'Retry', 'statement': 'The service shall retry an unacknowledged price.',
         'designItems': []},
    ],
    'items': [
        {'reqId': 'GAS-7', 'liveReqId': 'GAS-7', 'kind': 'DESIGN', 'parents': ['GAS-3'], 'title': 'Price queue',
         'statement': 'A queue per station holds the prices to send.', 'rationale': ''},
    ],
    'allocated': {'GAS-5': 'publisher'},
}
CONTEXT_JSON = json.dumps(CONTEXT)


def answer(*findings):
    return json.dumps({'findings': list(findings)})


SPLIT_3 = {'kind': 'ALLOCATION_PROPOSAL', 'subject': 'GAS-3', 'shares': [
    {'element': 'publisher', 'text': 'The service shall send every new price to each station.'},
    {'element': 'ack-tracker', 'text': 'The service shall record which price each station acknowledged.'}],
    'text': 'sending and tracking are two elements'}
SINGLE_4 = {'kind': 'ALLOCATION_PROPOSAL', 'subject': 'GAS-4', 'element': 'publisher', 'text': 'the publisher resends'}


# ==================== inputs ====================

def test_context_of_reads_the_context():
    c = ap.context_of(CONTEXT_JSON)
    assert [e['code'] for e in c['elements']] == ['ack-tracker', 'publisher']
    assert [t['reqId'] for t in c['topLevel']] == ['GAS-3', 'GAS-4']
    assert c['allocated'] == {'GAS-5': 'publisher'}


def test_context_of_a_missing_allocated_map_reads_as_empty():
    raw = dict(CONTEXT)
    del raw['allocated']
    assert ap.context_of(json.dumps(raw))['allocated'] == {}


@pytest.mark.parametrize('raw, message', [
    ('', 'is not JSON'),
    ('[]', 'no elements, topLevel and items lists'),
    (json.dumps({**CONTEXT, 'elements': []}), 'has no element'),
    (json.dumps({**CONTEXT, 'topLevel': []}), 'no requirement to allocate'),
    (json.dumps({**CONTEXT, 'elements': [{'name': 'x'}]}), 'an element with no code'),
    (json.dumps({**CONTEXT, 'items': [{'title': 'x'}]}), 'an entry of items with no reqId'),
])
def test_context_of_refuses(raw, message):
    with pytest.raises(ValueError, match=message):
        ap.context_of(raw)


# ==================== prompt ====================

def test_compose_carries_the_elements_the_design_and_the_requirements():
    prompt = ap.compose(ap.context_of(CONTEXT_JSON))
    assert '- ack-tracker: Acknowledgement tracker - keeps which station holds which price' in prompt
    assert '- publisher: Price publisher\n' in prompt
    assert '- GAS-5 -> publisher' in prompt
    assert 'Design item GAS-7 (DESIGN): Price queue\n    A queue per station holds the prices to send.' in prompt
    assert 'Requirement GAS-3: Settle on the latest price\n    The service shall make every station display' in prompt
    assert '    Design items: GAS-7' in prompt
    assert 'Requirement GAS-4 (now GAS-9): Retry' in prompt
    assert prompt.index('The elements:') < prompt.index('Requirements to allocate:')


def test_compose_without_design_or_allocations():
    prompt = ap.compose(ap.context_of(json.dumps({**CONTEXT, 'items': [], 'allocated': {}})))
    assert 'The design items:' not in prompt
    assert 'allocated already' not in prompt
    assert 'Design items:' not in prompt, 'a design item the context does not hold is not named'


# ==================== check ====================

def test_findings_of_canonical_form_in_context_order():
    out = ap.findings_of(answer(SINGLE_4, SPLIT_3), ap.context_of(CONTEXT_JSON))
    assert [f['subject'] for f in out['findings']] == ['GAS-3', 'GAS-4']
    assert out['findings'][0] == {'kind': 'ALLOCATION_PROPOSAL', 'subject': 'GAS-3', 'shares': SPLIT_3['shares'],
                                  'text': 'sending and tracking are two elements'}
    assert out['findings'][1] == {'kind': 'ALLOCATION_PROPOSAL', 'subject': 'GAS-4', 'element': 'publisher',
                                  'text': 'the publisher resends'}


def test_findings_of_unwraps_one_fence_and_reads_a_missing_kind_and_a_null_element():
    split = {k: v for k, v in SPLIT_3.items() if k != 'kind'}
    split['element'] = None
    raw = '```json\n' + answer(split, SINGLE_4) + '\n```'
    out = ap.findings_of(raw, ap.context_of(CONTEXT_JSON))
    assert out['findings'][0]['kind'] == 'ALLOCATION_PROPOSAL'
    assert 'element' not in out['findings'][0]


@pytest.mark.parametrize('cc_result, message', [
    ('not json', 'not JSON'),
    (json.dumps({'proposals': []}), r'no \{"findings"'),
    (answer(SPLIT_3), 'proposed nothing for GAS-4'),
    (answer(SPLIT_3, SINGLE_4, SINGLE_4), 'GAS-4 a second time'),
    (answer(SPLIT_3, {**SINGLE_4, 'subject': 'GAS-5'}), "'GAS-5', which is not a requirement to allocate"),
    (answer(SPLIT_3, {**SINGLE_4, 'kind': 'TRACE_PROPOSAL'}), 'unknown kind'),
    (answer(SPLIT_3, {**SINGLE_4, 'counterpart': 'x'}), "unknown field 'counterpart'"),
    (answer(SPLIT_3, {**SINGLE_4, 'text': ' '}), 'has no text'),
    (answer(SPLIT_3, {**SINGLE_4, 'element': 'storage'}), "unknown element 'storage'"),
    (answer(SPLIT_3, {**SINGLE_4, 'shares': SPLIT_3['shares']}), 'exactly one of an element and shares'),
    (answer(SPLIT_3, {k: v for k, v in SINGLE_4.items() if k != 'element'}), 'exactly one of an element and shares'),
    (answer({**SPLIT_3, 'shares': SPLIT_3['shares'][:1]}, SINGLE_4), 'fewer than two shares'),
    (answer({**SPLIT_3, 'shares': [SPLIT_3['shares'][0], SPLIT_3['shares'][0]]}, SINGLE_4), 'two shares'),
    (answer({**SPLIT_3, 'shares': [SPLIT_3['shares'][0], {'element': 'ack-tracker', 'text': ''}]}, SINGLE_4), 'has no text'),
    (answer({**SPLIT_3, 'shares': [SPLIT_3['shares'][0], {'element': 'ack-tracker', 'text': 'ж' * 1001}]}, SINGLE_4),
     'over 2000 UTF-8 bytes'),
    (answer({**SPLIT_3, 'shares': [SPLIT_3['shares'][0], {'element': 'ack-tracker', 'text': 'x', 'why': 'y'}]}, SINGLE_4),
     "unknown field 'why'"),
])
def test_findings_of_refuses(cc_result, message):
    with pytest.raises(ValueError, match=message):
        ap.findings_of(cc_result, ap.context_of(CONTEXT_JSON))
