# nrvv_cc_answer (plan 045 Phase 36): the decode every NRVV check applies to CC's stored answer.

import json

import pytest

import nrvv_cc_answer as ca

ANSWER = {'findings': [{'kind': 'GAP', 'text': 'a "quoted" word } and a brace'}]}


@pytest.mark.parametrize('tail', ['', '\n', '\r\n', '}', '}\r\n', '"}', ' "}}\n', ']', '}]"'])
def test_a_whole_value_followed_by_whitespace_and_stray_closers_is_read(tail):
    assert ca.loads(json.dumps(ANSWER) + tail) == ANSWER


@pytest.mark.parametrize('tail', [' {"findings": []}', ' and some prose', '{', '[', ',', 'x}', '}{'])
def test_anything_else_after_the_value_is_refused(tail):
    with pytest.raises(ValueError, match='CC answered something that is not JSON'):
        ca.loads(json.dumps(ANSWER) + tail)


@pytest.mark.parametrize('text', ['', 'not json', '"}', 'findings: []'])
def test_an_answer_that_does_not_start_with_a_json_value_is_refused(text):
    with pytest.raises(ValueError, match='CC answered something that is not JSON'):
        ca.loads(text)


def test_the_refusal_carries_an_excerpt_of_at_most_300_characters():
    with pytest.raises(ValueError) as e:
        ca.loads('x' * 1000)
    assert str(e.value) == 'CC answered something that is not JSON: ' + 'x' * 300 + '...'
