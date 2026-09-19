# The batch-paths Function's core: which record is taken, and which of its lines become branches. Every path is
# built under the test's own tmp_path, so every expected answer is written down before the code runs.

import json
import re

import pytest

import mh_rg_batch_paths as fn


def records(*bodies):
    return json.dumps([{'type': 'mh.asset.dir-batch-for-requirements.2', 'recKey': 'batch-' + str(i + 1).zfill(4),
                        'body': body} for i, body in enumerate(bodies)])


# ---------------------------------------------------------------------------------------------------
# the record

def test_the_record_is_the_one_that_was_selected():
    record = fn.the_record(records('C:\\x\\A.java'))

    assert record['recKey'] == 'batch-0001'
    assert record['body'] == 'C:\\x\\A.java'


@pytest.mark.parametrize('records_json, phrase', [
    ('not json', 'not JSON'),
    ('{"recKey": "batch-0001", "body": "x"}', 'not a JSON array'),
    ('[]', 'no record was selected'),
    (records('a', 'b'), 'exactly one selected record, got 2: batch-0001, batch-0002'),
    (json.dumps([{'recKey': 'batch-0001', 'body': None}]), 'no string body'),
    (json.dumps(['batch-0001']), 'no string body'),
])
def test_the_record_refuses(records_json, phrase):
    with pytest.raises(ValueError, match=phrase):
        fn.the_record(records_json)


# ---------------------------------------------------------------------------------------------------
# the paths

def test_batch_paths_are_the_stripped_non_blank_lines_in_the_bodys_order(tmp_path):
    b, a, c = (str(tmp_path / name) for name in ('b.java', 'a.java', 'c.java'))
    body = '\n' + b + '\n\n  ' + a + '  \r\n' + c + '\n'

    assert fn.batch_paths(body, 'batch-0001') == [b, a, c]


def test_batch_paths_keep_a_generated_hundred_whole_and_in_order(tmp_path):
    paths = [str(tmp_path / ('F' + str(i).zfill(3) + '.java')) for i in range(100)]

    assert fn.batch_paths('\n'.join(paths), 'batch-0004') == paths


def test_batch_paths_refuse_an_empty_body():
    with pytest.raises(ValueError, match="record 'batch-0001' has an empty body"):
        fn.batch_paths(' \n \r\n', 'batch-0001')


def test_batch_paths_refuse_a_relative_path_naming_it(tmp_path):
    with pytest.raises(ValueError, match="not an absolute path: 'src/B.java'"):
        fn.batch_paths(str(tmp_path / 'A.java') + '\nsrc/B.java', 'batch-0001')


def test_batch_paths_refuse_a_path_listed_twice_naming_it(tmp_path):
    a = str(tmp_path / 'A.java')

    with pytest.raises(ValueError, match=re.escape("listed more than once: '" + a + "'")):
        fn.batch_paths(a + '\n' + str(tmp_path / 'B.java') + '\n' + a, 'batch-0001')


def test_batch_paths_name_every_problem_at_once(tmp_path):
    a = str(tmp_path / 'A.java')

    with pytest.raises(ValueError) as e:
        fn.batch_paths('x.java\n' + a + '\n' + a + '\ny.java', 'batch-0007')

    message = str(e.value)
    assert message.startswith("record 'batch-0007' refused before any file was processed: ")
    assert message.count('not an absolute path') == 2
    assert message.count('listed more than once') == 1
