# The check Function's core: a branch's CC answer, checked and written as exactly one line.

import json

import pytest

import mh_rg_req_check as fn

REQ = {'name': 'Start', 'content': 'Derby shall start.', 'rationale': 'The file starts it.'}


def test_answer_line_carries_the_path_and_the_checked_requirements(tmp_path):
    path = str(tmp_path / 'Engine.java')

    line = fn.answer_line('  ' + path + '\n', json.dumps([REQ]))

    assert json.loads(line) == {'sourcePath': path, 'requirements': [REQ]}


def test_answer_line_is_one_ascii_line_whatever_the_requirements_say(tmp_path):
    content = 'Derby shall\nnever lose\u2028a committed \u2013 transaction.'
    unusual = {'name': '\u00dcberblick', 'content': content, 'rationale': 'Kapitel 1\r\nsagt es.'}

    line = fn.answer_line(str(tmp_path / 'Engine.java'), json.dumps([unusual]))

    assert line.isascii()
    assert line.splitlines() == [line]
    assert json.loads(line)['requirements'] == [unusual]


def test_answer_line_unwraps_a_markdown_fence_as_the_store_does(tmp_path):
    line = fn.answer_line(str(tmp_path / 'Engine.java'), '```json\n' + json.dumps([REQ]) + '\n```')

    assert json.loads(line)['requirements'] == [REQ]


@pytest.mark.parametrize('cc_result, phrase', [
    ('not json', 'not JSON'),
    ('[]', 'no requirements'),
    (json.dumps([dict(REQ, content='too short')]), '#1 content must be text of at least 3 words'),
    (json.dumps([REQ, dict(REQ, rationale=' ')]), '#2 has no rationale'),
])
def test_answer_line_refuses_an_answer_the_store_would_refuse(tmp_path, cc_result, phrase):
    with pytest.raises(ValueError, match=phrase):
        fn.answer_line(str(tmp_path / 'Engine.java'), cc_result)


def test_answer_line_refuses_a_branch_that_was_handed_no_path():
    with pytest.raises(ValueError, match='source-path is empty'):
        fn.answer_line(' \n', json.dumps([REQ]))
