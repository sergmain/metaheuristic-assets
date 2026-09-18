# The prompt Function's core, against files the tests write into tmp_path - the real filesystem, disposable.

import json

import pytest

import mh_rg_req_prompt as fn


def records(*pairs):
    return json.dumps([{'type': 'mh.asset.dir-batch-for-requirements.2', 'recKey': k, 'body': b} for k, b in pairs])


def test_first_path_is_the_first_line_of_the_body(tmp_path):
    a, b = str(tmp_path / 'a.html'), str(tmp_path / 'b.md')

    assert fn.first_path(records(('batch-0001', a + '\n' + b))) == a


def test_first_path_takes_the_first_record_by_rec_key(tmp_path):
    a, b = str(tmp_path / 'a.html'), str(tmp_path / 'b.html')

    assert fn.first_path(records(('batch-0002', b), ('batch-0001', a))) == a


def test_first_path_skips_leading_blank_lines(tmp_path):
    a = str(tmp_path / 'a.html')

    assert fn.first_path(records(('batch-0001', '\n  \n' + a + '\n'))) == a


@pytest.mark.parametrize('records_json, phrase', [
    ('not json', 'not JSON'),
    ('[]', 'empty'),
    ('{}', 'empty'),
    (json.dumps([{'recKey': 'batch-0001'}]), 'string body'),
    (json.dumps([{'recKey': 'batch-0001', 'body': ' \n '}]), 'empty body'),
    (json.dumps([{'recKey': 'batch-0001', 'body': 'relative/path.txt'}]), 'not an absolute path'),
])
def test_first_path_refuses(records_json, phrase):
    with pytest.raises(ValueError, match=phrase):
        fn.first_path(records_json)


def test_read_capped_returns_the_file(tmp_path):
    p = tmp_path / 'BUILDING.md'
    # bytes, not text mode: on Windows text mode would write \r\n, and the file is returned exactly as it is
    p.write_bytes('Derby builds with Ant.\n'.encode('utf-8'))

    assert fn.read_capped(str(p), 1000) == 'Derby builds with Ant.\n'


def test_read_capped_refuses_a_file_over_the_cap(tmp_path):
    p = tmp_path / 'big.md'
    p.write_bytes(b'x' * 11)

    with pytest.raises(ValueError, match='over the 10-byte cap'):
        fn.read_capped(str(p), 10)


def test_read_capped_fails_for_a_missing_file(tmp_path):
    with pytest.raises(OSError):
        fn.read_capped(str(tmp_path / 'missing.md'), 10)


@pytest.mark.parametrize('value, expected', [(None, 300000), ('', 300000), (' 5000 ', 5000)])
def test_parse_max_file_bytes(value, expected):
    assert fn.parse_max_file_bytes(value) == expected


@pytest.mark.parametrize('value', ['0', 'big'])
def test_parse_max_file_bytes_refuses(value):
    with pytest.raises(ValueError, match='max-file-bytes'):
        fn.parse_max_file_bytes(value)


def test_compose_prompt_carries_the_description_the_document_and_the_contract():
    prompt = fn.compose_prompt(' Requirements for java-based database Derby ', 'C:\\derby\\BUILDING.html',
                               '<h1>Building Derby</h1>')

    assert 'Project: Requirements for java-based database Derby\n' in prompt
    assert 'Source document: C:\\derby\\BUILDING.html\n' in prompt
    assert '<<<DOCUMENT\n<h1>Building Derby</h1>\nDOCUMENT>>>\n' in prompt
    assert 'between 1 and 5 requirements' in prompt
    assert '"name"' in prompt and '"content"' in prompt and '"rationale"' in prompt
    assert 'mh_cc_store_result (server mhcc)' in prompt
