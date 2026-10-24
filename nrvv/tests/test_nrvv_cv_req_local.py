# The LOCAL_CONTRADICTION check's prompt and check (nrvv_cv_req_local), on a requirement of the gas-price scenario and its
# candidates.

import json
import os

import pytest

import nrvv_cv_req_local as wf

PUBLISH = 'The service shall send each station the latest desired price.'
FIRST = 'The service shall keep the first price each station receives.'

SUBJECT = {
    'reqId': 'GASL-10', 'section': None, 'title': 'Latest price', 'statement': PUBLISH,
    'rationale': 'need: GASL-1 r1\nreading: GASL-20\nevidence: GASL-1 "the latest price"',
    'candidates': [
        {'reqId': 'GASL-11', 'why': 'child', 'section': None, 'title': 'Resend',
         'statement': 'The sender resends the latest desired price until it is acknowledged.'},
        {'reqId': 'GASL-20', 'why': 'reading GASL-20', 'section': 'NRVV:INTERPRETATION', 'title': 'Publishing',
         'statement': 'Publishing is met when the station ends up holding the latest desired price.'},
        {'reqId': 'GASL-12', 'why': 'same NEED', 'section': None, 'title': 'First price', 'statement': FIRST},
        {'reqId': 'GASL-13', 'why': 'interface', 'section': 'NRVV:INTERFACE', 'title': 'Set price',
         'statement': 'An operation sets the desired price of one station.'},
        {'reqId': 'GASL-14', 'why': 'shares 2 term(s)', 'section': 'GASL-30', 'title': 'Other', 'statement': 'Other words.'},
    ]}
LONE = {'reqId': 'GASL-40', 'section': 'NRVV:ENVIRONMENT', 'title': 'World', 'statement': 'Sends arrive out of order.',
        'rationale': '', 'candidates': []}
CONTEXT = {'subjects': [SUBJECT, LONE]}


def answer(subject, *pairs):
    return json.dumps({'subject': subject,
                       'contradictions': [{'counterpart': pairs[i], 'text': pairs[i + 1]} for i in range(0, len(pairs), 2)]})


def refusal(raw, chunk='GASL-10'):
    out = wf.checked(raw, CONTEXT, chunk + '\n')
    assert set(out.keys()) == {'refused', 'subjects'}, out
    assert out['subjects'] == [chunk]
    return out['refused']


# ---- the prompt ----

def test_prompt_states_what_a_contradiction_is_and_the_rules():
    p = wf.compose(SUBJECT)
    assert 'Two requirements contradict when there is a situation the world can present' in p
    assert 'Judge contradiction only' in p
    assert 'being more specific is no contradiction' in p
    assert 'A requirement contradicts an ASSUMPTION when it' in p
    assert 'OPEN_CHOICE when it fixes the dimension the item leaves open' in p
    assert 'Name only candidates, each once' in p


def test_prompt_lists_the_subject_and_each_candidate_with_why_and_section():
    p = wf.compose(SUBJECT)
    assert 'Requirement to judge: GASL-10: Latest price\n  ' + PUBLISH in p
    assert '  Rationale: need: GASL-1 r1 | reading: GASL-20 | evidence: GASL-1 "the latest price"' in p
    assert 'Candidate GASL-11 (child): Resend' in p
    assert 'Candidate GASL-20 (reading GASL-20, interpretation item): Publishing' in p
    assert 'Candidate GASL-13 (interface, Interface item): Set price' in p
    assert 'Candidate GASL-14 (shares 2 term(s), in section GASL-30): Other' in p
    assert '  ' + FIRST in p
    assert p.index('Candidate GASL-11 ') < p.index('Candidate GASL-20 ') < p.index('Candidate GASL-12 '), 'nearest first'


def test_prompt_of_a_subject_without_candidates():
    p = wf.compose(LONE)
    assert 'Requirement to judge: GASL-40 (Environment item): World' in p
    assert 'Candidates: none - the list of contradictions is empty.' in p
    assert 'Rationale:' not in p


def test_prompt_ends_with_the_answer_instruction():
    p = wf.compose(SUBJECT)
    assert p.index('Candidates:') < p.index('Answer by calling the mh_cc_store_result tool')
    assert wf.ANSWER_SHAPE in p
    assert p.endswith('Print nothing - neither the contradictions nor any explanation: only what the tool stores reaches the'
                      ' pipeline.')


# ---- the check: accepted answers ----

def test_contradictions_on_candidates_in_canonical_form():
    out = wf.checked(answer(' GASL-10 ', ' GASL-12 ', '  a station sent its first price and then a later one  '),
                     CONTEXT, 'GASL-10\n')
    assert out == {'subject': 'GASL-10',
                   'contradictions': [{'counterpart': 'GASL-12', 'text': 'a station sent its first price and then a later one'}]}


def test_no_contradiction_and_a_subject_without_candidates():
    assert wf.checked(answer('GASL-10'), CONTEXT, 'GASL-10') == {'subject': 'GASL-10', 'contradictions': []}
    assert wf.checked(answer('GASL-40'), CONTEXT, 'GASL-40') == {'subject': 'GASL-40', 'contradictions': []}


def test_a_contradiction_carries_its_direction():
    # plan 050 Phase 9 (decision 11): which side the items the two are read under support - optional, a string
    raw = json.dumps({'subject': 'GASL-10', 'contradictions': [
        {'counterpart': 'GASL-12', 'text': 'a first price, then a later one', 'direction': ' GASL-20 supports GASL-10 '},
        {'counterpart': 'GASL-11', 'text': 'a resend'}]})
    out = wf.checked(raw, CONTEXT, 'GASL-10\n')
    assert out['contradictions'][0] == {'counterpart': 'GASL-12', 'text': 'a first price, then a later one',
                                        'direction': 'GASL-20 supports GASL-10'}
    assert 'direction' not in out['contradictions'][1], 'no direction given - none'
    bad = json.dumps({'subject': 'GASL-10', 'contradictions': [{'counterpart': 'GASL-12', 'text': 't', 'direction': 7}]})
    assert 'has a direction that is not a string' in refusal(bad)
    assert '"direction"' in wf.ANSWER_SHAPE and 'which of the two the governing items support' in wf.compose(SUBJECT)


def test_one_markdown_fence_is_unwrapped():
    out = wf.checked('```json\n' + answer('GASL-10', 'GASL-20', 'the reading drops a superseded price') + '\n```',
                     CONTEXT, 'GASL-10')
    assert [c['counterpart'] for c in out['contradictions']] == ['GASL-20']


# ---- the check: refusals (the Task succeeds, the store records the refusal) ----

def test_not_json_is_refused():
    assert 'not JSON' in refusal('no contradiction')


def test_not_the_answer_object_is_refused():
    assert 'no {"subject": ..., "contradictions": [...]} object' in refusal(json.dumps({'contradictions': []}))
    assert 'no {"subject": ..., "contradictions": [...]} object' in refusal(
        json.dumps({'subject': 'GASL-10', 'contradictions': [], 'note': 'x'}))
    assert 'no {"subject": ..., "contradictions": [...]} object' in refusal(
        json.dumps({'subject': 'GASL-10', 'contradictions': 'GASL-12'}))


def test_an_answer_on_another_requirement_is_refused():
    assert "CC answered on 'GASL-12', not on the requirement judged GASL-10" in refusal(answer('GASL-12'))


def test_a_counterpart_that_is_not_a_candidate_is_refused():
    assert "names 'GASL-40', which is not a candidate of GASL-10" in refusal(answer('GASL-10', 'GASL-40', 't'))
    assert "names 'GASL-10', which is not a candidate of GASL-10" in refusal(answer('GASL-10', 'GASL-10', 't'))
    assert "names 'GASL-12', which is not a candidate of GASL-40" in refusal(answer('GASL-40', 'GASL-12', 't'), 'GASL-40')


def test_a_counterpart_named_twice_is_refused():
    assert 'names GASL-12 a second time' in refusal(answer('GASL-10', 'GASL-12', 't', 'GASL-12', 'u'))


def test_an_unknown_field_or_no_situation_is_refused():
    raw = json.dumps({'subject': 'GASL-10', 'contradictions': [{'counterpart': 'GASL-12', 'text': 't', 'kind': 'HARD'}]})
    assert "unknown field 'kind'" in refusal(raw)
    assert 'names no situation in which the two cannot both hold' in refusal(answer('GASL-10', 'GASL-12', ' '))
    raw = json.dumps({'subject': 'GASL-10', 'contradictions': [{'counterpart': 'GASL-12', 'text': 7}]})
    assert 'has a text that is not a string' in refusal(raw)
    assert 'is not an object' in refusal(json.dumps({'subject': 'GASL-10', 'contradictions': ['GASL-12']}))


# ---- defects of the flow raise ----

@pytest.mark.parametrize('chunk, message', [
    ('', 'the chunk names 0 subjects'),
    ('GASL-10\nGASL-40', 'the chunk names 2 subjects'),
    ('GASL-99', "the chunk names 'GASL-99', which is not a subject of the local contradiction context"),
])
def test_a_chunk_that_is_not_one_subject_of_the_context_raises(chunk, message):
    with pytest.raises(ValueError) as e:
        wf.checked(answer('GASL-10'), CONTEXT, chunk)
    assert message in str(e.value)


@pytest.mark.parametrize('raw, message', [
    ('not json', 'the local contradiction context is not JSON'),
    (json.dumps({'needs': []}), 'the local contradiction context has no subjects list'),
    (json.dumps({'subjects': [{'title': 'x'}]}), 'a subject with no reqId or no candidates list'),
    (json.dumps({'subjects': [{'reqId': 'A-1', 'candidates': 'B-1'}]}), 'a subject with no reqId or no candidates list'),
])
def test_a_broken_context_raises(raw, message):
    with pytest.raises(ValueError) as e:
        wf.context_of(raw)
    assert message in str(e.value)


# ---- the Functions ----

def _task(tmp_path, metas, inputs, outputs):
    work = tmp_path / 'work'
    for i, (name, text) in enumerate(inputs.items()):
        p = work / 'variable' / str(i + 1)
        os.makedirs(p.parent, exist_ok=True)
        p.write_text(text, encoding='utf-8')
    return {'workingPath': str(work), 'metas': [{k: v} for k, v in metas.items()],
            'inputs': [{'name': name, 'id': i + 1, 'dataType': 'variable'} for i, name in enumerate(inputs)],
            'outputs': [{'name': name, 'id': 100 + i} for i, name in enumerate(outputs)]}


def test_run_prompt_and_run_check(tmp_path):
    task = _task(tmp_path / 'p', {'variable-for-local-cv-context': 'localCvContext', 'variable-for-subjects': 'subject',
                                  'variable-for-prompt': 'localCvPrompt'},
                 {'localCvContext': json.dumps(CONTEXT), 'subject': 'GASL-10\n'}, ['localCvPrompt'])
    wf.run_prompt(task, 'mh.asset.nrvv-cv-req-local-prompt_1.0')
    prompt = (tmp_path / 'p' / 'work' / 'artifacts' / '100').read_text(encoding='utf-8')
    assert 'Requirement to judge: GASL-10' in prompt and 'GASL-40' not in prompt

    metas = {'variable-for-cc-result': 'localCvResult', 'variable-for-local-cv-context': 'localCvContext',
             'variable-for-subjects': 'subject', 'variable-for-findings': 'findings'}
    task = _task(tmp_path / 'c', metas, {'localCvResult': answer('GASL-10', 'GASL-12', 'first and latest'),
                                         'localCvContext': json.dumps(CONTEXT), 'subject': 'GASL-10\n'}, ['findings'])
    wf.run_check(task, 'mh.asset.nrvv-cv-req-local-check_1.0')
    stored = json.loads((tmp_path / 'c' / 'work' / 'artifacts' / '100').read_text(encoding='utf-8'))
    assert stored == {'subject': 'GASL-10', 'contradictions': [{'counterpart': 'GASL-12', 'text': 'first and latest'}]}

    task = _task(tmp_path / 'r', metas, {'localCvResult': answer('GASL-10', 'GASL-40', 't'),
                                         'localCvContext': json.dumps(CONTEXT), 'subject': 'GASL-10\n'}, ['findings'])
    wf.run_check(task, 'mh.asset.nrvv-cv-req-local-check_1.0')
    stored = json.loads((tmp_path / 'r' / 'work' / 'artifacts' / '100').read_text(encoding='utf-8'))
    assert stored['subjects'] == ['GASL-10'] and 'not a candidate of GASL-10' in stored['refused']
