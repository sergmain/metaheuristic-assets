# The needs CV's prompt and check (plan 045, Phase 9): nrvv_needs_cv.

import json

import pytest

import nrvv_needs_cv as cv

SCENARIO = ('The pricing team needs every gas station to show a new price. Only eventual correctness matters, where '
            'each station must settle on the latest price.')
LATENCY = 'The pricing team needs to know within one minute that a station holds a new price.'

TRACE = [
    {'needReqId': 'GAS-1', 'revision': 2, 'title': 'Gas stations settle on the latest price', 'statement': SCENARIO,
     'requirements': [
         {'reqId': 'GAS-6', 'liveReqId': 'GAS-6',
          'text': 'GAS-6 Stations settle\n1. Requirement content\n1.1) The service shall make every station settle.',
          'rationale': 'need: GAS-1 r1\nassumed: stations report what they hold'},
         {'reqId': 'GAS-7', 'liveReqId': 'GAS-9', 'text': 'GAS-9 Edition\n1.1) The amended text.', 'rationale': ''},
         {'reqId': 'GAS-8', 'liveReqId': None, 'text': '', 'rationale': ''}]},
    {'needReqId': 'GAS-2', 'revision': 1, 'title': 'Stations acknowledge within one minute', 'statement': LATENCY,
     'requirements': []},
]
TRACE_JSON = json.dumps(TRACE)


# ==================== inputs ====================

def test_trace_of_reads_the_trace():
    assert [n['needReqId'] for n in cv.trace_of(TRACE_JSON)] == ['GAS-1', 'GAS-2']
    assert cv.trace_of('[]') == []


@pytest.mark.parametrize('raw', ['', 'not json', '{}', json.dumps([{'needReqId': 'GAS-1'}]),
                                 json.dumps([{'requirements': []}])])
def test_trace_of_refuses(raw):
    with pytest.raises(ValueError):
        cv.trace_of(raw)


def test_traced_by_need_holds_roots_and_live_members():
    assert cv.traced_by_need(TRACE) == {'GAS-1': {'GAS-6', 'GAS-7', 'GAS-9', 'GAS-8'}, 'GAS-2': set()}


# ==================== prompt ====================

def test_compose_carries_every_need_and_its_trace():
    prompt = cv.compose(TRACE)
    assert 'NEED GAS-1 (revision 2): Gas stations settle on the latest price' in prompt
    assert SCENARIO in prompt
    assert LATENCY in prompt
    assert 'Traces to requirement GAS-6:' in prompt
    assert '    1.1) The service shall make every station settle.' in prompt
    assert 'Traces to requirement GAS-7 (now GAS-9):' in prompt
    assert 'Traces to GAS-8, which is obsolete at this snapshot.' in prompt
    assert 'It traces to no requirement.' in prompt
    assert 'INCOHERENT_TRACE' in prompt
    assert 'Do not report the "assumed: ..." items' in prompt
    assert '{"findings": [{"kind": "<kind>", "subject": "<NEED reqId>"' in prompt


def test_compose_without_needs():
    assert 'The project has no agreed NEED.' in cv.compose([])


# ==================== check ====================

def test_findings_of_canonical_form():
    answer = cv.findings_of(json.dumps({'findings': [
        {'kind': 'CONTRADICTION', 'subject': 'GAS-2', 'counterpart': 'GAS-1', 'text': ' one minute vs eventual '},
        {'kind': 'INCOHERENT_TRACE', 'subject': 'GAS-1', 'counterpart': 'GAS-9', 'text': 'GAS-9 serves revision 1'},
        {'kind': 'GAP', 'subject': 'GAS-1', 'counterpart': None, 'text': 'who sets a price'}]}), TRACE)
    assert answer == {'findings': [
        {'kind': 'CONTRADICTION', 'subject': 'GAS-2', 'counterpart': 'GAS-1', 'text': 'one minute vs eventual'},
        {'kind': 'INCOHERENT_TRACE', 'subject': 'GAS-1', 'counterpart': 'GAS-9', 'text': 'GAS-9 serves revision 1'},
        {'kind': 'GAP', 'subject': 'GAS-1', 'text': 'who sets a price'}]}


def test_findings_of_unwraps_one_fence_and_accepts_no_finding():
    assert cv.findings_of('```json\n{"findings": []}\n```', TRACE) == {'findings': []}


@pytest.mark.parametrize('answer, message', [
    ('not json', 'not JSON'),
    ('{"findings": [], "verdict": "ok"}', 'no {"findings"'),
    ('{"findings": [{"kind": "ASSUMPTION", "subject": "GAS-1", "text": "x"}]}', 'unknown kind'),
    ('{"findings": [{"kind": "GAP", "subject": "GAS-1", "text": "x", "fix": "y"}]}', 'unknown field'),
    ('{"findings": [{"kind": "GAP", "subject": "GAS-1", "text": " "}]}', 'no text'),
    ('{"findings": [{"kind": "GAP", "subject": "GAS-6", "text": "x"}]}', 'not one of the agreed NEEDs'),
    ('{"findings": [{"kind": "CONTRADICTION", "subject": "GAS-1", "text": "x"}]}', 'names no other agreed NEED'),
    ('{"findings": [{"kind": "REDUNDANCY", "subject": "GAS-1", "counterpart": "GAS-1", "text": "x"}]}',
     'names no other agreed NEED'),
    ('{"findings": [{"kind": "INCOHERENT_TRACE", "subject": "GAS-2", "counterpart": "GAS-6", "text": "x"}]}',
     'names no requirement GAS-2 traces to'),
    ('{"findings": [{"kind": "VAGUE_TERM", "subject": "GAS-1", "counterpart": "GAS-77", "text": "x"}]}',
     'neither another agreed NEED'),
])
def test_findings_of_refuses(answer, message):
    with pytest.raises(ValueError, match=message):
        cv.findings_of(answer, TRACE)
