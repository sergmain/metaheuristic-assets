import os

import pytest

import mh_task_io as io


def test_variable_name_is_the_meta_value():
    assert io.variable_name([{'variable-for-prompt': 'ccPrompt'}], 'prompt') == 'ccPrompt'


def test_variable_name_refuses_a_missing_meta_and_lists_what_is_declared():
    with pytest.raises(ValueError, match='variable-for-prompt') as e:
        io.variable_name([{'variable-for-output': 'ccResult'}], 'prompt')
    assert 'variable-for-output' in str(e.value)


def test_roles_follow_the_processors_layout(tmp_path):
    (tmp_path / 'variable').mkdir()
    (tmp_path / 'variable' / '31').write_text('Derby', encoding='utf-8')
    task = {
        'workingPath': str(tmp_path),
        'metas': [{'variable-for-description': 'projectDescription'}, {'variable-for-prompt': 'ccPrompt'}],
        'inputs': [{'name': 'projectDescription', 'id': 31, 'dataType': 'variable'}],
        'outputs': [{'name': 'ccPrompt', 'id': 32}],
    }

    assert io.read_role(task, 'description') == 'Derby'
    target = io.output_role(task, 'prompt')
    assert target == os.path.join(str(tmp_path), 'artifacts', '32')
    io.write_text(target, 'the prompt')
    assert (tmp_path / 'artifacts' / '32').read_text(encoding='utf-8') == 'the prompt'


def test_a_role_bound_to_an_undeclared_variable_fails_naming_what_is_declared(tmp_path):
    task = {'workingPath': str(tmp_path), 'metas': [{'variable-for-description': 'nope'}],
            'inputs': [{'name': 'projectDescription', 'id': 31}]}

    with pytest.raises(ValueError, match='projectDescription'):
        io.read_role(task, 'description')


def test_a_nullified_input_reads_as_none(tmp_path):
    # MH marks a nullified input 'empty' and downloads no file for it - there is nothing to open
    task = {'workingPath': str(tmp_path), 'metas': [{'variable-for-description': 'projectDescription'}],
            'inputs': [{'name': 'projectDescription', 'id': 31, 'empty': True}]}

    assert io.read_role(task, 'description') is None


def test_a_missing_file_that_is_not_nullified_still_fails(tmp_path):
    # no file WITHOUT the empty mark is a defect, not a null
    task = {'workingPath': str(tmp_path), 'metas': [{'variable-for-description': 'projectDescription'}],
            'inputs': [{'name': 'projectDescription', 'id': 31}]}

    with pytest.raises(FileNotFoundError):
        io.read_role(task, 'description')
