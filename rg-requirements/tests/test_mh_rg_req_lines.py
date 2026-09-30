# The req-lines Function's core: one checked answer in, one store-req line per requirement out. Every answer is made
# by running the producer - mh.asset.rg-req-check_1.0's own answer_line - so the input is byte for byte what the
# branch hands this Function (DAHF-IMPLEMENTATION 0.13: synthetic content, real format). The content is invented.

import json

import pytest

import mh_rg_req_lines as fn
from mh_rg_req_check import answer_line

PATH = 'C:\\synthetic\\corpus\\Alpha.java'


def cc(*requirements):
    return json.dumps(list(requirements))


def req(content, name='A synthetic requirement', rationale='SYNTHETIC fixture - why it matters.'):
    r = {'content': content, 'rationale': rationale}
    if name is not None:
        r['name'] = name
    return r


def test_every_requirement_becomes_one_line_in_ccs_order():
    answer = answer_line(PATH, cc(req('The first synthetic requirement must hold at all times.', 'First'),
                                  req('The second synthetic requirement must hold at all times.', 'Second'),
                                  req('The third synthetic requirement must hold at all times.', 'Third')))

    source, lines = fn.requirement_lines(answer)

    assert source == PATH
    assert [json.loads(line)['name'] for line in lines] == ['First', 'Second', 'Third']
    assert json.loads(lines[1]) == {'name': 'Second',
                                    'content': 'The second synthetic requirement must hold at all times.',
                                    'rationale': 'SYNTHETIC fixture - why it matters.'}


def test_a_line_carries_only_the_fields_store_req_reads():
    answer = answer_line(PATH, cc(req('The synthetic requirement must hold at all times.')))

    _, lines = fn.requirement_lines(answer)

    assert list(json.loads(lines[0]).keys()) == ['name', 'content', 'rationale']


def test_an_absent_name_is_left_out_not_written_empty():
    answer = answer_line(PATH, cc(req('The synthetic requirement must hold at all times.', name=None)))

    _, lines = fn.requirement_lines(answer)

    assert 'name' not in json.loads(lines[0])


def test_a_newline_and_a_line_separator_inside_a_requirement_stay_on_one_line():
    answer = answer_line(PATH, cc(req('The synthetic requirement must hold\nacross two lines \u2028 and a separator.')))

    _, lines = fn.requirement_lines(answer)

    assert len(lines) == 1
    assert len('\n'.join(lines).splitlines()) == 1
    assert json.loads(lines[0])['content'] == 'The synthetic requirement must hold\nacross two lines \u2028 and a separator.'


@pytest.mark.parametrize('answer_text, phrase', [
    ('', 'expected exactly one answer line'),
    ('{"a": 1}\n{"b": 2}', 'expected exactly one answer line'),
    ('not json', 'not JSON'),
    ('{"sourcePath": "C:\\\\x", "requirements": []}', 'at least one requirement'),
    ('{"sourcePath": "C:\\\\x"}', 'at least one requirement'),
    ('["x"]', 'at least one requirement'),
    ('{"sourcePath": "C:\\\\x", "requirements": ["x"]}', 'requirement #1 is not an object'),
    ('{"sourcePath": "C:\\\\x", "requirements": [{"content": "ok content here"}, {"content": " "}]}', 'requirement #2 has no content'),
])
def test_a_malformed_answer_is_refused(answer_text, phrase):
    with pytest.raises(ValueError, match=phrase):
        fn.requirement_lines(answer_text)
