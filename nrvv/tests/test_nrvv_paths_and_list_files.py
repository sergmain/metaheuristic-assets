# The path contract inside a run workspace, and the file listing that feeds the recovery split. Every tree is built
# under the test's own tmp_path, so every expected answer is written down before the code runs.

import os

import pytest

import nrvv_list_files as lf
import nrvv_paths as paths
from conftest import write


# ---------------------------------------------------------------------------------------------------
# the path contract

def test_each_role_has_its_own_checkout_under_the_workspace(tmp_path):
    ws = str(tmp_path / 'ws')
    assert paths.checkout_root(ws, 'source') == os.path.join(ws, 'source')
    assert paths.checkout_root(ws, 'test-suite') == os.path.join(ws, 'test-suite')
    assert paths.checkout_root(ws, 'target') == os.path.join(ws, 'target')
    assert paths.verification_dir(ws) == os.path.join(ws, 'verification')


def test_dir_path_is_the_relative_dir_inside_the_checkout(tmp_path):
    ws = str(tmp_path / 'ws')
    assert paths.dir_path(ws, 'test-suite', 'nrvv/synthetic/test-suite') == \
        os.path.join(ws, 'test-suite', 'nrvv', 'synthetic', 'test-suite')
    assert paths.dir_path(ws, 'target', 'a\\b/') == os.path.join(ws, 'target', 'a', 'b')


def test_an_empty_dir_is_the_repository_root(tmp_path):
    ws = str(tmp_path / 'ws')
    assert paths.dir_path(ws, 'target', '') == os.path.join(ws, 'target')
    assert paths.dir_path(ws, 'target', None) == os.path.join(ws, 'target')
    assert paths.rel_posix('') == ''


def test_rel_posix_is_gits_spelling():
    assert paths.rel_posix('a\\b/') == 'a/b'
    assert paths.rel_posix('./a/./b') == 'a/b'


@pytest.mark.parametrize('bad', ['../x', 'a/../../x', '/abs', '\\abs', 'C:/x'])
def test_a_dir_pointing_outside_the_checkout_is_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        paths.dir_path(str(tmp_path), 'target', bad)


def test_a_relative_workspace_is_refused():
    with pytest.raises(ValueError, match='absolute'):
        paths.checkout_root('relative/ws', 'target')


def test_an_unknown_role_is_refused(tmp_path):
    with pytest.raises(ValueError, match='role'):
        paths.checkout_root(str(tmp_path), 'tests')


# ---------------------------------------------------------------------------------------------------
# glob matching

@pytest.mark.parametrize('glob, rel, expected', [
    ('**/*.java', 'A.java', True),
    ('**/*.java', 'a/b/A.java', True),
    ('**/*.java', 'A.txt', False),
    ('*.java', 'A.java', True),
    ('*.java', 'a/A.java', False),
    ('src/**', 'src/a/b.txt', True),
    ('src/**', 'srcx/a.txt', False),
    ('**/test/**', 'a/test/B.java', True),
    ('**/test/**', 'test/B.java', True),
    ('**/test/**', 'a/testing/B.java', False),
    ('?.py', 'a.py', True),
    ('?.py', 'ab.py', False),
    ('a.b', 'axb', False),
])
def test_glob_to_regex(glob, rel, expected):
    assert bool(lf.glob_to_regex(glob).match(rel)) is expected


# ---------------------------------------------------------------------------------------------------
# the listing

def tree(root):
    write(root, {
        'src/main/A.java': 'a',
        'src/main/B.java': 'b',
        'src/test/ATest.java': 't',
        'README.md': 'r',
        '.git/hooks/x.java': 'never listed',
    })


def test_include_and_exclude_globs(tmp_path):
    root = str(tmp_path / 'repo')
    tree(root)

    assert lf.list_files(root, ['**/*.java'], ['**/test/**']) == [
        os.path.abspath(os.path.join(root, 'src', 'main', 'A.java')),
        os.path.abspath(os.path.join(root, 'src', 'main', 'B.java')),
    ]


def test_several_include_globs_and_sorted_output(tmp_path):
    root = str(tmp_path / 'repo')
    tree(root)

    assert lf.list_files(root, ['*.md', 'src/test/**'], []) == sorted([
        os.path.abspath(os.path.join(root, 'README.md')),
        os.path.abspath(os.path.join(root, 'src', 'test', 'ATest.java')),
    ])


def test_no_include_glob_lists_nothing(tmp_path):
    root = str(tmp_path / 'repo')
    tree(root)

    assert lf.list_files(root, [], []) == []


def test_dot_git_is_never_entered(tmp_path):
    root = str(tmp_path / 'repo')
    tree(root)

    assert not any('.git' in p.split(os.sep) for p in lf.list_files(root, ['**'], []))


@pytest.mark.parametrize('text, expected', [(None, []), ('', []), ('  ', []), ('["**/*.java"]', ['**/*.java'])])
def test_parse_globs(text, expected):
    assert lf.parse_globs(text) == expected


@pytest.mark.parametrize('text', ['"**/*.java"', '[1]', '{"a": 1}'])
def test_parse_globs_refuses_anything_but_an_array_of_strings(text):
    with pytest.raises(ValueError):
        lf.parse_globs(text)
