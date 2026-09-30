# The first/others split: requirement #1 of the batch's first file becomes the genesis, every other requirement a
# store-req line. The answers are made by running the producer - mh.asset.rg-req-check_1.0's answer_line - and joined
# the way internal mh.aggregate (type text) joins them, with a blank line (DETAILS 8.2). Content is invented.

import json

import pytest

import mh_rg_req_first as fn
from mh_rg_req_check import answer_line

A = 'C:\\synthetic\\corpus\\Alpha.java'
B = 'C:\\synthetic\\corpus\\Beta.java'


def req(name, content):
    return {'name': name, 'content': content, 'rationale': 'SYNTHETIC fixture - ' + name + '.'}


def answers(*lines):
    return '\n\n'.join(lines)


ALPHA = answer_line(A, json.dumps([req('A1', 'Alpha requirement one must always hold.'),
                                   req('A2', 'Alpha requirement two must always hold.')]))
BETA = answer_line(B, json.dumps([req('B1', 'Beta requirement one must always hold.')]))


def test_requirement_one_of_the_first_file_is_the_genesis_whatever_order_the_answers_arrived_in():
    first_path, first_answer, others = fn.first_and_others(A + '\n' + B, answers(BETA, ALPHA))

    assert first_path == A
    first = json.loads(first_answer)
    assert first['sourcePath'] == A
    assert [r['name'] for r in first['requirements']] == ['A1'], 'requirement #1 ALONE'
    assert [json.loads(line)['name'] for line in others] == ['A2', 'B1'], 'the rest, in the batch order'


def test_the_first_answer_is_one_line_the_batch_store_parses_as_a_batch_of_one():
    _, first_answer, _ = fn.first_and_others(A + '\n' + B, answers(ALPHA, BETA))

    assert len(first_answer.splitlines()) == 1
    # the batch store's own parse, over exactly what it will be handed: first-path as the batch, this as the answers
    from mh_rg_req_store_batch import parse_answers, plan
    assert plan(A, parse_answers(first_answer)) == [(A, json.loads(first_answer)['requirements'][0])]


def test_an_other_line_carries_only_the_fields_store_req_reads_and_no_source_line():
    _, _, others = fn.first_and_others(A + '\n' + B, answers(ALPHA, BETA))

    b1 = json.loads(others[1])
    assert list(b1.keys()) == ['name', 'content', 'rationale']
    assert b1 == {'name': 'B1', 'content': 'Beta requirement one must always hold.',
                  'rationale': 'SYNTHETIC fixture - B1.'}


def test_a_batch_of_one_requirement_has_no_others():
    single = answer_line(A, json.dumps([req('A1', 'Alpha requirement one must always hold.')]))

    first_path, _, others = fn.first_and_others(A, single)

    assert first_path == A
    assert others == []


def test_a_file_without_an_answer_stops_the_split_before_anything_is_stored():
    with pytest.raises(ValueError, match='1 of the 2 files have no answer: ' + B.replace('\\', '\\\\')):
        fn.first_and_others(A + '\n' + B, answers(ALPHA))
