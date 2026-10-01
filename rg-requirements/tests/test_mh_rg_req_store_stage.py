# The per-file store into an OPEN STAGE: which STAGE id is accepted, what is written for each requirement, and what a
# failure says. The answer is made by the real producer - mh.asset.rg-req-check_1.0's answer_line - so the input is
# byte for byte what a branch hands this Function (DAHF-IMPLEMENTATION 0.13). The write stands in for RG's HTTP
# requirements/manual, the one call that leaves the process; the content is invented.

import json

import pytest

import mh_rg_req_store_stage as fn
from mh_rg_req_check import answer_line
from mh_rg_req_store_batch import parse_answers, plan, requirements_to_store

PATH = 'C:\\synthetic\\corpus\\Alpha.java'


def cc(*contents):
    return json.dumps([{'name': 'Synthetic ' + str(i + 1), 'content': c, 'rationale': 'SYNTHETIC fixture - why.'}
                       for i, c in enumerate(contents)])


def planned(*contents):
    return requirements_to_store(plan(PATH, parse_answers(answer_line(PATH, cc(*contents)))))


def rg_write(answers):
    """RG's requirements/manual as seen from here: each call answers the next reqId in turn."""
    sent = []

    def post(body):
        sent.append(body)
        return answers[len(sent) - 1]
    return post, sent


@pytest.mark.parametrize('text, stage', [('23', 23), (' 23\n', 23), ('1', 1)])
def test_a_stage_id_is_a_positive_whole_number(text, stage):
    assert fn.stage_id(text) == stage


@pytest.mark.parametrize('text, phrase', [(None, 'is empty'), ('  ', 'is empty'), ('null', 'not a snapshot id'),
                                          ('0', 'not a snapshot id'), ('-4', 'not a snapshot id')])
def test_anything_else_is_refused_before_rg_is_called(text, phrase):
    with pytest.raises(ValueError, match=phrase):
        fn.stage_id(text)


def test_every_requirement_of_the_file_is_written_into_the_named_stage_in_order():
    post, sent = rg_write(['TMPSYNTH01-7', 'TMPSYNTH01-9'])

    ids = fn.store_into_stage(planned('The first synthetic requirement must hold.',
                                      'The second synthetic requirement must hold.'), 23, post)

    assert ids == ['TMPSYNTH01-7', 'TMPSYNTH01-9']
    assert [body['snapshotId'] for body in sent] == [23, 23]
    assert [body['content'] for body in sent] == ['The first synthetic requirement must hold.',
                                                  'The second synthetic requirement must hold.']


def test_every_rationale_names_its_file():
    post, sent = rg_write(['TMPSYNTH01-1'])

    fn.store_into_stage(planned('The synthetic requirement must hold at all times.'), 23, post)

    assert sent[0]['rationale'] == 'SYNTHETIC fixture - why.\n\nsource: ' + PATH


def test_a_refused_write_names_the_stage_and_what_was_already_written_into_it():
    def post(body):
        if body['content'].startswith('The second'):
            raise RuntimeError('RG refused the requirement: synthetic refusal')
        return 'TMPSYNTH01-3'

    with pytest.raises(RuntimeError, match='synthetic refusal - written into STAGE 23 before the failure, NOT committed: '
                                           'TMPSYNTH01-3'):
        fn.store_into_stage(planned('The first synthetic requirement must hold.',
                                    'The second synthetic requirement must hold.'), 23, post)


def test_nothing_to_store_is_refused():
    with pytest.raises(ValueError, match='nothing to store'):
        fn.store_into_stage([], 23, rg_write([])[0])
