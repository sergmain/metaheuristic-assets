# checkout, guard and commit-push against a bare remote the test builds itself (conftest.GitWorld).

import os

import pytest

import nrvv_checkout as co
import nrvv_commit_push as cp
import nrvv_git
import nrvv_guard as guard
from conftest import git, write

FILES = {
    'nrvv/test-suite/tests/test_a.py': 'def test_a():\n    assert True\n',
    'nrvv/target/app.py': 'X = 1\n',
    'README.md': 'r\n',
}


def loc(world, branch='main', d=''):
    return {'url': world.url, 'branchOrRef': branch, 'dir': d}


# ---------------------------------------------------------------------------------------------------
# checkout

def test_checkout_resolves_the_branch_tip_and_returns_the_dir_path(world, tmp_path):
    sha = world.init(FILES)
    ws = str(tmp_path / 'ws')

    got_sha, got_dir = co.checkout(ws, 'target', loc(world, d='nrvv/target'))

    assert got_sha == sha
    assert got_dir == os.path.join(ws, 'target', 'nrvv', 'target')
    with open(os.path.join(got_dir, 'app.py'), encoding='utf-8') as f:
        assert f.read() == 'X = 1\n'


def test_checkout_is_idempotent_by_sha(world, tmp_path):
    sha = world.init(FILES)
    ws = str(tmp_path / 'ws')
    co.checkout(ws, 'target', loc(world))

    again, _ = co.checkout(ws, 'target', loc(world))

    assert again == sha
    assert nrvv_git.is_clean(os.path.join(ws, 'target'))


def test_checkout_resets_a_dirty_tree_from_a_failed_attempt(world, tmp_path):
    world.init(FILES)
    ws = str(tmp_path / 'ws')
    co.checkout(ws, 'target', loc(world))
    root = os.path.join(ws, 'target')
    write(root, {'nrvv/target/app.py': 'X = 2\n', 'junk.txt': 'left behind'})

    co.checkout(ws, 'target', loc(world))

    assert not os.path.exists(os.path.join(root, 'junk.txt'))
    with open(os.path.join(root, 'nrvv', 'target', 'app.py'), encoding='utf-8') as f:
        assert f.read() == 'X = 1\n'


def test_checkout_follows_a_new_commit_on_the_branch(world, tmp_path):
    world.init(FILES)
    ws = str(tmp_path / 'ws')
    co.checkout(ws, 'target', loc(world))
    new_sha = world.push_change({'nrvv/target/app.py': 'X = 3\n'})

    got, _ = co.checkout(ws, 'target', loc(world))

    assert got == new_sha


def test_a_full_sha_pins_the_checkout(world, tmp_path):
    first = world.init(FILES)
    world.push_change({'nrvv/target/app.py': 'X = 3\n'})
    ws = str(tmp_path / 'ws')

    got, d = co.checkout(ws, 'target', loc(world, branch=first, d='nrvv/target'))

    assert got == first
    with open(os.path.join(d, 'app.py'), encoding='utf-8') as f:
        assert f.read() == 'X = 1\n'


def test_an_unknown_ref_is_an_error(world, tmp_path):
    world.init(FILES)
    with pytest.raises(nrvv_git.GitError, match='not found'):
        co.checkout(str(tmp_path / 'ws'), 'target', loc(world, branch='no-such-branch'))


@pytest.mark.parametrize('text', [None, '', '[]', '{"branchOrRef": "main"}', '{"url": "u"}',
                                  '{"url": "u", "branchOrRef": "main", "dir": "../x"}'])
def test_parse_location_refuses_an_incomplete_or_escaping_location(text):
    with pytest.raises(ValueError):
        co.parse_location(text)


def test_parse_location_defaults_dir_to_the_root():
    assert co.parse_location('{"url": "u", "branchOrRef": "main"}')['dir'] == ''
    assert co.parse_location('{"url": "u", "branchOrRef": "main", "dir": null}')['dir'] == ''


# ---------------------------------------------------------------------------------------------------
# guard

def test_paths_outside_is_a_prefix_check_on_whole_segments():
    paths = ['nrvv/target/a.py', 'nrvv/target/sub/b.py', 'nrvv/targetx/c.py', 'nrvv/test-suite/t.py', 'README.md']
    assert guard.paths_outside(paths, 'nrvv/target') == ['nrvv/targetx/c.py', 'nrvv/test-suite/t.py', 'README.md']
    assert guard.paths_outside(paths, '') == []


def test_guard_refuses_a_change_under_the_test_suite_dir(world, tmp_path):
    world.init(FILES)
    ws = str(tmp_path / 'ws')
    base, _ = co.checkout(ws, 'target', loc(world, d='nrvv/target'))
    root = os.path.join(ws, 'target')
    write(root, {'nrvv/target/app.py': 'X = 2\n', 'nrvv/test-suite/tests/test_a.py': 'def test_a():\n    pass\n'})

    with pytest.raises(guard.GuardError) as e:
        guard.check(root, base, 'nrvv/target')

    # exactly the one offender, spelled in full - a truncated or extra path is a wrong guard
    assert str(e.value).endswith("'nrvv/target': nrvv/test-suite/tests/test_a.py")


def test_changed_paths_spells_every_path_in_full(world, tmp_path):
    # the first porcelain entry of an unstaged change starts with a space (' M path'); it must survive intact
    world.init(FILES)
    ws = str(tmp_path / 'ws')
    base, _ = co.checkout(ws, 'target', loc(world))
    root = os.path.join(ws, 'target')
    write(root, {'nrvv/target/app.py': 'X = 2\n', 'untracked.txt': 'u'})

    assert nrvv_git.changed_paths(root, base) == ['nrvv/target/app.py', 'untracked.txt']


def test_guard_passes_changes_under_the_allowed_dir_only(world, tmp_path):
    world.init(FILES)
    ws = str(tmp_path / 'ws')
    base, _ = co.checkout(ws, 'target', loc(world, d='nrvv/target'))
    root = os.path.join(ws, 'target')
    write(root, {'nrvv/target/app.py': 'X = 2\n', 'nrvv/target/new/module.py': 'Y = 1\n'})

    assert guard.check(root, base, 'nrvv/target') == ['nrvv/target/app.py', 'nrvv/target/new/module.py']


def test_guard_sees_a_committed_change_outside_too(world, tmp_path):
    world.init(FILES)
    ws = str(tmp_path / 'ws')
    base, _ = co.checkout(ws, 'target', loc(world, d='nrvv/target'))
    root = os.path.join(ws, 'target')
    write(root, {'README.md': 'rewritten\n'})
    git(root, 'add', '-A')
    git(root, 'commit', '-q', '-m', 'sneaky')

    with pytest.raises(guard.GuardError, match='README.md'):
        guard.check(root, base, 'nrvv/target')


def test_guard_counts_both_sides_of_a_rename_out_of_the_allowed_dir(world, tmp_path):
    world.init(FILES)
    ws = str(tmp_path / 'ws')
    base, _ = co.checkout(ws, 'target', loc(world, d='nrvv/target'))
    root = os.path.join(ws, 'target')
    git(root, 'mv', 'nrvv/target/app.py', 'app.py')

    with pytest.raises(guard.GuardError, match='app.py'):
        guard.check(root, base, 'nrvv/target')


# ---------------------------------------------------------------------------------------------------
# commit-push

def test_commit_and_push_moves_the_remote_branch_to_the_new_commit(world, tmp_path):
    world.init(FILES)
    ws = str(tmp_path / 'ws')
    base, _ = co.checkout(ws, 'target', loc(world, d='nrvv/target'))
    root = os.path.join(ws, 'target')
    write(root, {'nrvv/target/app.py': 'X = 42\n'})

    sha = cp.commit_and_push(root, loc(world), 'nrvv: implementation')

    assert sha != base
    assert world.tip('main') == sha
    assert git(world.bare, 'show', sha + ':nrvv/target/app.py') == 'X = 42'


def test_nothing_to_commit_returns_the_base_and_leaves_the_remote_alone(world, tmp_path):
    first = world.init(FILES)
    ws = str(tmp_path / 'ws')
    co.checkout(ws, 'target', loc(world))

    sha = cp.commit_and_push(os.path.join(ws, 'target'), loc(world), 'nrvv: nothing')

    assert sha == first
    assert world.tip('main') == first


def test_basic_auth_header():
    # base64('user:tok') == 'dXNlcjp0b2s='
    assert cp.basic_auth_header('user:tok') == 'Authorization: Basic dXNlcjp0b2s='
    with pytest.raises(ValueError):
        cp.basic_auth_header('no-colon')


# ---------------------------------------------------------------------------------------------------
# commit-push onto a branch that moved after the checkout (plan 043, Phase 7)

def test_commit_and_push_lands_on_a_branch_that_moved_in_another_directory(world, tmp_path):
    world.init(FILES)
    ws = str(tmp_path / 'ws')
    co.checkout(ws, 'target', loc(world, d='nrvv/target'))
    root = os.path.join(ws, 'target')
    write(root, {'nrvv/target/app.py': 'X = 42\n'})
    # another run (or the executor) pushes to the same branch meanwhile, in another directory
    other = world.push_change({'nrvv/test-suite/tests/test_b.py': 'def test_b():\n    assert True\n'})

    # CT Green-1 (043 Phase 7): the push is refused - the branch moved after the checkout - and the Task fails
    # (git's refusal: '! [rejected]        HEAD -> main (fetch first)')
    # CT Red (043 Phase 7): the run's commit is cherry-picked onto the moved tip and pushed again - both commits are
    # on the branch and the output is the new tip
    sha = cp.commit_and_push(root, loc(world), 'nrvv: implementation')

    assert world.tip('main') == sha
    git(world.bare, 'merge-base', '--is-ancestor', other, sha)
    assert git(world.bare, 'show', sha + ':nrvv/target/app.py') == 'X = 42'
    assert git(world.bare, 'show', sha + ':nrvv/test-suite/tests/test_b.py').startswith('def test_b():')
    assert git(world.bare, 'log', '-1', '--format=%s', sha) == 'nrvv: implementation'


def test_commit_and_push_fails_with_gits_conflict_when_the_branch_moved_in_the_same_file(world, tmp_path):
    world.init(FILES)
    ws = str(tmp_path / 'ws')
    co.checkout(ws, 'target', loc(world, d='nrvv/target'))
    root = os.path.join(ws, 'target')
    write(root, {'nrvv/target/app.py': 'X = 42\n'})
    other = world.push_change({'nrvv/target/app.py': 'X = 7\n'})

    with pytest.raises(nrvv_git.GitError) as e:
        cp.commit_and_push(root, loc(world), 'nrvv: implementation')

    assert 'CONFLICT' in str(e.value) and 'nrvv/target/app.py' in str(e.value), str(e.value)
    assert world.tip('main') == other, 'nothing of the run landed'


def test_commit_and_push_lands_every_commit_of_the_run_when_the_branch_moved(world, tmp_path):
    world.init(FILES)
    ws = str(tmp_path / 'ws')
    co.checkout(ws, 'target', loc(world, d='nrvv/target'))
    root = os.path.join(ws, 'target')
    # the implementer committed once by itself; commit-push commits what is left
    write(root, {'nrvv/target/app.py': 'X = 42\n'})
    git(root, 'add', '-A')
    git(root, 'commit', '-q', '-m', 'implementer commit')
    write(root, {'nrvv/target/util.py': 'Y = 1\n'})
    other = world.push_change({'README.md': 'moved\n'})

    sha = cp.commit_and_push(root, loc(world), 'nrvv: implementation')

    assert world.tip('main') == sha
    assert git(world.bare, 'log', '--format=%s', '-3', sha).splitlines() == ['nrvv: implementation', 'implementer commit', 'change']
    git(world.bare, 'merge-base', '--is-ancestor', other, sha)
    assert git(world.bare, 'show', sha + ':nrvv/target/app.py') == 'X = 42'
    assert git(world.bare, 'show', sha + ':README.md') == 'moved'


def test_commit_and_push_with_nothing_committed_leaves_a_moved_branch_alone(world, tmp_path):
    first = world.init(FILES)
    ws = str(tmp_path / 'ws')
    co.checkout(ws, 'target', loc(world))
    other = world.push_change({'README.md': 'moved\n'})

    sha = cp.commit_and_push(os.path.join(ws, 'target'), loc(world), 'nrvv: nothing')

    assert sha == first, 'the checkout commit: nothing of the run to land'
    assert world.tip('main') == other


def test_commit_and_push_refused_for_another_reason_fails_at_once(world, tmp_path):
    world.init(FILES)
    ws = str(tmp_path / 'ws')
    co.checkout(ws, 'target', loc(world))
    root = os.path.join(ws, 'target')
    write(root, {'nrvv/target/app.py': 'X = 42\n'})
    nowhere = {'url': str(tmp_path / 'nowhere.git'), 'branchOrRef': 'main', 'dir': ''}

    with pytest.raises(nrvv_git.GitError) as e:
        cp.commit_and_push(root, nowhere, 'nrvv: implementation')

    assert 'git push' in str(e.value) and '[rejected]' not in str(e.value), str(e.value)
