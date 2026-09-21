# The path-prompt Function's core: the one path a branch is handed, and the prompt built from that file. The
# files are written by the tests into their own tmp_path.

import pytest

import mh_rg_req_path_prompt as fn


# ---------------------------------------------------------------------------------------------------
# the path

def test_the_path_is_the_one_line_the_branch_was_handed_stripped(tmp_path):
    path = str(tmp_path / 'Engine.java')

    assert fn.the_path('  ' + path + '\r\n') == path


@pytest.mark.parametrize('text, phrase', [
    ('', 'source-path is empty'),
    (' \n \n', 'source-path is empty'),
    ('relative/Engine.java', 'not an absolute path'),
])
def test_the_path_refuses(text, phrase):
    with pytest.raises(ValueError, match=phrase):
        fn.the_path(text)


def test_the_path_refuses_more_than_one_line(tmp_path):
    with pytest.raises(ValueError, match='holds 2 lines, expected exactly one path'):
        fn.the_path(str(tmp_path / 'A.java') + '\n' + str(tmp_path / 'B.java'))


# ---------------------------------------------------------------------------------------------------
# the prompt

def test_prompt_for_puts_the_description_the_path_and_the_whole_file_into_the_prompt(tmp_path):
    source = tmp_path / 'Engine.java'
    # bytes, not write_text: on Windows text mode would turn the \n into \r\n and change what is asserted
    source.write_bytes(b'class Engine {}\n')

    prompt, characters = fn.prompt_for(str(source), '  Requirements for Derby \n', 1000)

    assert characters == 16
    assert 'Project: Requirements for Derby\n' in prompt
    assert 'Source document: ' + str(source) + '\n' in prompt
    assert '<<<DOCUMENT\nclass Engine {}\nDOCUMENT>>>\n' in prompt
    assert 'mh_cc_store_result' in prompt


def test_prompt_for_refuses_a_file_over_the_cap(tmp_path):
    source = tmp_path / 'Big.java'
    source.write_bytes(b'x' * 11)

    with pytest.raises(ValueError, match='11 bytes, over the 10-byte cap'):
        fn.prompt_for(str(source), 'Requirements for Derby', 10)


@pytest.mark.parametrize('description', ['', '   \n', None])
def test_prompt_for_refuses_an_empty_description(tmp_path, description):
    source = tmp_path / 'Engine.java'
    source.write_bytes(b'class Engine {}\n')

    with pytest.raises(ValueError, match='description is empty'):
        fn.prompt_for(str(source), description, 1000)


def test_prompt_for_fails_for_a_file_that_is_not_there(tmp_path):
    with pytest.raises(OSError):
        fn.prompt_for(str(tmp_path / 'Gone.java'), 'Requirements for Derby', 1000)
