# Plan 047 Phase 26 (decision 19): nrvv_git retries git's network-class failures. The scripted failures are git's own
# exit-128 messages for a host that does not resolve; every attempt after them runs the real git, and the assertions
# are on what git() returns or raises.

import subprocess

import pytest

import nrvv_git

HOST_FAILURE = "fatal: unable to access 'https://bitbucket.org/x/y.git/': Could not resolve host: bitbucket.org"


def failing_first(failures, stderr=HOST_FAILURE, returncode=128):
    """subprocess.run, after `failures` runs that end with git's `returncode` and `stderr`."""
    calls = {'n': 0}

    def run(cmd, **kwargs):
        calls['n'] += 1
        if calls['n'] <= failures:
            return subprocess.CompletedProcess(cmd, returncode, '', stderr)
        return subprocess.run(cmd, **kwargs)
    return run


def no_wait(_seconds):
    pass


def test_the_retry_delays():
    assert nrvv_git.RETRY_DELAYS == (10, 20, 30, 30, 30)


@pytest.mark.parametrize('returncode, output, expected', [
    (128, HOST_FAILURE, True),
    (128, "fatal: unable to access 'https://x/': Failed to connect to x port 443: Connection timed out", True),
    (128, 'ssh: connect to host github.com port 22: Connection timed out', True),
    (128, "fatal: unable to access 'https://x/': The requested URL returned error: 403", True),
    (128, "fatal: not a git repository (or any of the parent directories): .git", False),
    (128, "fatal: couldn't find remote ref refs/heads/nope", False),
    (1, HOST_FAILURE, False),
    (128, None, False),
])
def test_is_network_failure(returncode, output, expected):
    assert nrvv_git.is_network_failure(returncode, output) is expected


def test_a_host_failure_is_retried_and_the_third_attempt_succeeds():
    out = nrvv_git.git(['--version'], run=failing_first(2), sleep=no_wait)
    assert out.startswith('git version'), out


def test_the_last_retry_failing_raises_with_the_attempts():
    with pytest.raises(nrvv_git.GitError) as e:
        nrvv_git.git(['ls-remote', 'https://bitbucket.org/x/y.git'], run=failing_first(100), sleep=no_wait)
    message = str(e.value)
    assert 'failed with exit 128 after ' + str(len(nrvv_git.RETRY_DELAYS) + 1) + ' attempts' in message, message
    assert 'Could not resolve host' in message


def test_a_failure_that_is_not_network_class_fails_at_once():
    with pytest.raises(nrvv_git.GitError) as e:
        nrvv_git.git(['status'], run=failing_first(1, stderr='fatal: not a git repository'), sleep=no_wait)
    assert str(e.value) == 'git status failed with exit 128: fatal: not a git repository'
