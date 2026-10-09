# Trace proposals' prompt and check (plan 045, Phase 17): nrvv_trace_proposal.

import json

import pytest

import nrvv_trace_proposal as tp

CONTEXT = {
    'snapshotId': 41,
    'needs': [
        {'reqId': 'GRT-1', 'revision': 1, 'title': 'Operators get a greeting',
         'statement': 'Operators need a greeting when the program runs.', 'gap': True},
        {'reqId': 'GRT-2', 'revision': 2, 'title': 'Runs are on record', 'statement': 'Operators need a record of runs.',
         'gap': False},
    ],
    'heldMembers': [
        {'reqId': 'GRT-20', 'sectionReqId': 'GRT-19', 'text': 'GRT-20 Standard output\n1.1) The greeting goes to standard output.'},
    ],
    'orphans': [
        {'reqId': 'GRT-5', 'liveReqId': 'GRT-5', 'topLevel': True,
         'text': 'GRT-5 Print greeting\n1. Requirement content\n1.1) The program shall print Hello.', 'rationale': 'NrvvSample.main'},
        {'reqId': 'GRT-6', 'liveReqId': 'GRT-9', 'topLevel': True, 'text': 'GRT-9 Exit code\n1.1) The program shall exit 0.',
         'rationale': ''},
        {'reqId': 'GRT-7', 'liveReqId': 'GRT-7', 'topLevel': False, 'text': 'GRT-7 Debug flag\n1.1) A -v flag prints timing.',
         'rationale': 'a\nmulti-line rationale'},
    ],
}
CONTEXT_JSON = json.dumps(CONTEXT)
CHUNK = ['GRT-5', 'GRT-6', 'GRT-7']


def answer(*findings):
    return json.dumps({'findings': list(findings)})


TRACE_5 = {'kind': 'TRACE_PROPOSAL', 'subject': 'GRT-5', 'counterpart': 'GRT-1', 'text': 'prints the greeting'}
COMPLY_6 = {'kind': 'COMPLIANCE_PROPOSAL', 'subject': 'GRT-6', 'counterpart': 'GRT-20', 'text': 'answers the standard'}
DROP_7 = {'kind': 'NOT_TO_PORT', 'subject': 'GRT-7', 'counterpart': None, 'text': 'a debug aid'}


# ==================== inputs ====================

def test_context_of_reads_the_context():
    c = tp.context_of(CONTEXT_JSON)
    assert [o['reqId'] for o in c['orphans']] == CHUNK
    assert tp.context_of(json.dumps({'needs': [], 'heldMembers': [], 'orphans': []}))['orphans'] == []


@pytest.mark.parametrize('raw', ['', 'not json', '[]', json.dumps({'needs': [], 'orphans': []}),
                                 json.dumps({'needs': [{'title': 'x'}], 'heldMembers': [], 'orphans': []})])
def test_context_of_refuses(raw):
    with pytest.raises(ValueError):
        tp.context_of(raw)


def test_chunk_of_reads_one_orphan_per_line():
    assert tp.chunk_of(' GRT-5 \n\nGRT-7\n', CONTEXT) == ['GRT-5', 'GRT-7']


@pytest.mark.parametrize('raw, message', [
    ('', 'names no orphan'),
    ('GRT-5\nGRT-1', "'GRT-1', which is not an orphan"),
    ('GRT-5\nGRT-5', 'an orphan twice'),
])
def test_chunk_of_refuses(raw, message):
    with pytest.raises(ValueError, match=message):
        tp.chunk_of(raw, CONTEXT)


# ==================== prompt ====================

def test_compose_carries_the_needs_the_held_requirements_and_the_chunk():
    prompt = tp.compose(CONTEXT, ['GRT-6', 'GRT-7'])
    assert 'NEED GRT-1 (revision 1), traces to nothing yet: Operators get a greeting' in prompt
    assert 'NEED GRT-2 (revision 2): Runs are on record' in prompt
    assert 'Operators need a record of runs.' in prompt
    assert 'Held requirement GRT-20 (section GRT-19):' in prompt
    assert '    1.1) The greeting goes to standard output.' in prompt
    assert 'Requirement GRT-6 (now GRT-9), top-level:' in prompt
    assert '    1.1) The program shall exit 0.' in prompt
    assert 'Requirement GRT-7, not top-level - NOT_TO_PORT only:' in prompt
    assert '    Rationale: a multi-line rationale' in prompt
    assert 'Requirement GRT-5' not in prompt, 'an orphan of another chunk is not listed'
    assert 'Exactly one proposal per listed requirement' in prompt
    assert '{"findings": [{"kind": "<kind>", "subject": "<requirement reqId>"' in prompt


def test_compose_without_needs_or_held_requirements():
    prompt = tp.compose({'needs': [], 'heldMembers': [], 'orphans': CONTEXT['orphans']}, ['GRT-5'])
    assert 'The project has no agreed NEED.' in prompt
    assert 'The project holds no imposed requirement.' in prompt


# ==================== check ====================

def test_findings_of_canonical_form_in_chunk_order():
    got = tp.findings_of(answer(DROP_7, dict(TRACE_5, subject=' GRT-5 ', text=' prints the greeting '), COMPLY_6),
                         CONTEXT, CHUNK)
    assert got == {'findings': [
        {'kind': 'TRACE_PROPOSAL', 'subject': 'GRT-5', 'counterpart': 'GRT-1', 'text': 'prints the greeting'},
        {'kind': 'COMPLIANCE_PROPOSAL', 'subject': 'GRT-6', 'counterpart': 'GRT-20', 'text': 'answers the standard'},
        {'kind': 'NOT_TO_PORT', 'subject': 'GRT-7', 'text': 'a debug aid'}]}


def test_findings_of_unwraps_one_fence():
    fenced = '```json\n' + answer(TRACE_5) + '\n```'
    assert tp.findings_of(fenced, CONTEXT, ['GRT-5'])['findings'][0]['subject'] == 'GRT-5'


@pytest.mark.parametrize('cc_result, message', [
    ('not json', 'not JSON'),
    ('{"findings": [], "verdict": "ok"}', 'no {"findings"'),
    (answer(dict(TRACE_5, kind='CONTRADICTION'), COMPLY_6, DROP_7), 'unknown kind'),
    (answer(dict(TRACE_5, fix='x'), COMPLY_6, DROP_7), 'unknown field'),
    (answer(dict(TRACE_5, text=' '), COMPLY_6, DROP_7), 'no text'),
    (answer(TRACE_5, COMPLY_6, DROP_7, dict(DROP_7, subject='GRT-8')), 'not a requirement of this chunk'),
    (answer(TRACE_5, COMPLY_6, DROP_7, DROP_7), 'GRT-7 a second time'),
    (answer(TRACE_5, COMPLY_6), 'proposed nothing for GRT-7'),
    (answer(dict(TRACE_5, counterpart='GRT-20'), COMPLY_6, DROP_7), 'names no agreed NEED'),
    (answer(TRACE_5, dict(COMPLY_6, counterpart='GRT-1'), DROP_7), 'names no imposed held requirement'),
    (answer(TRACE_5, COMPLY_6, dict(DROP_7, counterpart='GRT-1')), 'NOT_TO_PORT and names a counterpart'),
    (answer(TRACE_5, COMPLY_6, dict(TRACE_5, subject='GRT-7')), 'GRT-7, which is not top-level'),
])
def test_findings_of_refuses(cc_result, message):
    with pytest.raises(ValueError, match=message):
        tp.findings_of(cc_result, CONTEXT, CHUNK)
