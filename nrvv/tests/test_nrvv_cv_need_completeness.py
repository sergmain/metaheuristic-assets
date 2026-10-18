# The COMPLETENESS check's prompt and check (nrvv_cv_need_completeness), on r1's agreed NEEDs from
# tests/data/evidence-cases.json.

import json
import os

import pytest

import nrvv_cv_need_completeness as wf

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'evidence-cases.json'), encoding='utf-8') as f:
    TABLE = json.load(f)

NEEDS = {x['reqId']: x for x in TABLE['needs']}


def n(i):
    return 'GASV6A3-' + str(i)


def need(i):
    x = NEEDS[n(i)]
    return {'reqId': x['reqId'], 'revision': x['revision'], 'kind': x['kind'], 'title': 'T ' + x['reqId'],
            'statement': x['statement']}


READING = {'reqId': 'GASV7A1-20', 'kind': 'READING',
           'statement': 'Publishing an update is met when the station ends up holding the latest desired price.'}
OPEN_CHOICE = {'reqId': 'GASV7A1-21', 'kind': 'OPEN_CHOICE',
               'statement': 'How soon a station holds the latest price is not stated; requirements hold for every delay.'}
PUBLISH = {'reqId': 'GASV7A1-30', 'title': 'Latest price held',
           'statement': 'The service shall send a station the latest desired price until the station acknowledges it.',
           'rationale': 'need: GASV6A3-1 r1\nreading: GASV7A1-20\nevidence: GASV6A3-1 "publish gas price updates"'}
SETTLE = {'reqId': 'GASV7A1-31', 'title': 'Settle',
          'statement': 'The service shall resend the latest desired price after an acknowledgement of an older one.',
          'rationale': 'need: GASV6A3-4 r1\nevidence: GASV6A3-4 "settle on the latest price"'}

CONTEXT = {'subjects': [
    {'need': need(1), 'readings': [READING], 'requirements': [PUBLISH]},
    {'need': need(4), 'readings': [OPEN_CHOICE], 'requirements': [SETTLE]},
    {'need': need(8), 'readings': [], 'requirements': []},
]}
CHUNK = [n(1), n(4)]


def answer(*verdicts):
    return json.dumps({'verdicts': list(verdicts)})


def met(i, text=None):
    v = {'subject': n(i), 'verdict': 'MET'}
    if text is not None:
        v['text'] = text
    return v


def not_met(i, text):
    return {'subject': n(i), 'verdict': 'NOT_MET', 'text': text}


def refusal(raw, chunk=None):
    out = wf.checked(raw, CONTEXT, chunk or CHUNK)
    assert set(out.keys()) == {'refused', 'subjects'}, out
    assert out['subjects'] == (chunk or CHUNK), 'a refusal names every NEED of its chunk, in chunk order'
    return out['refused']


# ---- the prompt ----

def test_prompt_states_both_verdicts_and_the_rules():
    p = wf.compose(CONTEXT, CHUNK)
    assert '- MET:' in p and '- NOT_MET:' in p
    assert 'Judge completeness only' in p
    assert 'requirements that measure and report the' in p and 'never NOT_MET because no requirement bounds the cost' in p
    assert 'A dimension an OPEN_CHOICE item leaves open is not a gap' in p
    assert 'COST_OBJECTIVE - a cost' in p, 'the clause kinds are explained'


def test_prompt_lists_each_need_of_the_chunk_with_its_items_and_requirements():
    p = wf.compose(CONTEXT, CHUNK)
    assert 'NEED GASV6A3-1 (revision 1, OBLIGATION): T GASV6A3-1' in p
    assert '  ' + NEEDS[n(1)]['statement'] in p
    assert 'READING GASV7A1-20: ' + READING['statement'] in p
    assert 'OPEN_CHOICE GASV7A1-21: ' + OPEN_CHOICE['statement'] in p
    assert 'Requirement GASV7A1-30: Latest price held' in p
    assert '      ' + PUBLISH['statement'] in p
    assert 'Rationale: need: GASV6A3-1 r1 | reading: GASV7A1-20 | evidence: GASV6A3-1 "publish gas price updates"' in p
    assert p.index('NEED GASV6A3-1 ') < p.index('NEED GASV6A3-4 '), 'in chunk order'
    assert 'NEED GASV6A3-8 ' not in p, 'a NEED outside the chunk is not judged'


def test_prompt_marks_a_need_without_items_or_requirements():
    p = wf.compose(CONTEXT, [n(8)])
    assert 'NEED GASV6A3-8 (revision 1, COST_OBJECTIVE)' in p
    assert '  Governed by no item.' in p
    assert '  No top-level requirement cites this NEED.' in p


def test_prompt_ends_with_the_answer_instruction():
    p = wf.compose(CONTEXT, CHUNK)
    assert p.index('NEEDs to judge:') < p.index('Answer by calling the mh_cc_store_result tool')
    assert p.endswith('Print nothing - neither the verdicts nor any explanation: only what the tool stores reaches the'
                      ' pipeline.')
    assert wf.ANSWER_SHAPE in p


# ---- the check: accepted answers ----

def test_verdicts_come_back_in_chunk_order_with_only_their_fields():
    out = wf.checked(answer(not_met(4, 'a station acknowledges an old price after the latest was sent'), met(1)),
                     CONTEXT, CHUNK)
    assert out == {'verdicts': [{'subject': n(1), 'verdict': 'MET'},
                                {'subject': n(4), 'verdict': 'NOT_MET',
                                 'text': 'a station acknowledges an old price after the latest was sent'}]}


def test_a_met_verdict_keeps_its_text_and_a_blank_one_drops_it():
    out = wf.checked(answer(met(1, '  the reading is met  '), met(4, '  ')), CONTEXT, CHUNK)
    assert out['verdicts'] == [{'subject': n(1), 'verdict': 'MET', 'text': 'the reading is met'},
                               {'subject': n(4), 'verdict': 'MET'}]


def test_one_markdown_fence_is_unwrapped():
    out = wf.checked('```json\n' + answer(met(1), met(4)) + '\n```', CONTEXT, CHUNK)
    assert [v['verdict'] for v in out['verdicts']] == ['MET', 'MET']


# ---- the check: refusals (the Task succeeds, the store records the refusal) ----

def test_not_json_is_refused():
    assert 'not JSON' in refusal('the NEEDs are met')


def test_not_a_verdicts_object_is_refused():
    assert 'no {"verdicts": [...]} object' in refusal(json.dumps({'verdicts': [met(1), met(4)], 'note': 'x'}))
    assert 'no {"verdicts": [...]} object' in refusal(json.dumps({'findings': []}))


def test_an_unknown_field_is_refused():
    v = met(1)
    v['needReqIds'] = [n(1)]
    assert "unknown field 'needReqIds'" in refusal(answer(v, met(4)))


def test_an_unknown_verdict_is_refused():
    v = met(1)
    v['verdict'] = 'PARTLY_MET'
    assert "unknown verdict 'PARTLY_MET'" in refusal(answer(v, met(4)))


def test_a_subject_outside_the_chunk_is_refused():
    assert "names subject 'GASV6A3-8', which is not a NEED of this chunk" in refusal(answer(met(1), met(4), met(8)))


def test_a_subject_named_twice_is_refused():
    assert 'names GASV6A3-1 a second time' in refusal(answer(met(1), not_met(1, 'x'), met(4)))


def test_a_need_left_without_a_verdict_is_refused():
    assert 'CC gave no verdict on GASV6A3-4' in refusal(answer(met(1)))


def test_not_met_without_its_situation_is_refused():
    v = {'subject': n(4), 'verdict': 'NOT_MET'}
    assert 'is NOT_MET and names no situation' in refusal(answer(met(1), v))
    v['text'] = 42
    assert 'has a text that is not a string' in refusal(answer(met(1), v))


# ---- defects of the flow raise ----

def test_a_chunk_need_the_context_does_not_hold_raises():
    with pytest.raises(ValueError) as e:
        wf.checked(answer(met(1)), CONTEXT, [n(1), n(2)])
    assert "the chunk names 'GASV6A3-2', which is not a subject of the completeness context" in str(e.value)


def test_an_empty_or_repeated_chunk_raises():
    with pytest.raises(ValueError) as e:
        wf.chunk_of('\n  \n', CONTEXT)
    assert 'the chunk names no subject' in str(e.value)
    with pytest.raises(ValueError) as e:
        wf.chunk_of(n(1) + '\n' + n(1), CONTEXT)
    assert 'the chunk names a subject twice' in str(e.value)


@pytest.mark.parametrize('raw, message', [
    ('not json', 'the completeness context is not JSON'),
    (json.dumps({'needs': []}), 'the completeness context has no subjects list'),
    (json.dumps({'subjects': [{'need': {}}]}), 'a subject with no NEED reqId'),
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
            'inputs': [{'name': n, 'id': i + 1, 'dataType': 'variable'} for i, n in enumerate(inputs)],
            'outputs': [{'name': n, 'id': 100 + i} for i, n in enumerate(outputs)]}


def test_run_prompt_and_run_check(tmp_path):
    task = _task(tmp_path / 'p', {'variable-for-completeness-context': 'completenessContext',
                                  'variable-for-subjects': 'subjectChunk', 'variable-for-prompt': 'completenessPrompt'},
                 {'completenessContext': json.dumps(CONTEXT), 'subjectChunk': n(1) + '\n' + n(4) + '\n'},
                 ['completenessPrompt'])
    wf.run_prompt(task, 'mh.asset.nrvv-cv-need-completeness-prompt_1.0')
    prompt = (tmp_path / 'p' / 'work' / 'artifacts' / '100').read_text(encoding='utf-8')
    assert 'NEED GASV6A3-4 ' in prompt and 'NEED GASV6A3-8 ' not in prompt

    metas = {'variable-for-cc-result': 'completenessResult', 'variable-for-completeness-context': 'completenessContext',
             'variable-for-subjects': 'subjectChunk', 'variable-for-findings': 'findings'}
    task = _task(tmp_path / 'c', metas,
                 {'completenessResult': answer(met(1), not_met(4, 'an old acknowledgement')),
                  'completenessContext': json.dumps(CONTEXT), 'subjectChunk': n(1) + '\n' + n(4) + '\n'}, ['findings'])
    wf.run_check(task, 'mh.asset.nrvv-cv-need-completeness-check_1.0')
    stored = json.loads((tmp_path / 'c' / 'work' / 'artifacts' / '100').read_text(encoding='utf-8'))
    assert [(v['subject'], v['verdict']) for v in stored['verdicts']] == [(n(1), 'MET'), (n(4), 'NOT_MET')]

    task = _task(tmp_path / 'r', metas,
                 {'completenessResult': answer(met(1)), 'completenessContext': json.dumps(CONTEXT),
                  'subjectChunk': n(1) + '\n' + n(4) + '\n'}, ['findings'])
    wf.run_check(task, 'mh.asset.nrvv-cv-need-completeness-check_1.0')
    stored = json.loads((tmp_path / 'r' / 'work' / 'artifacts' / '100').read_text(encoding='utf-8'))
    assert stored['subjects'] == [n(1), n(4)] and 'CC gave no verdict on GASV6A3-4' in stored['refused']
