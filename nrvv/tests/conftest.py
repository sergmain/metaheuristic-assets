import os
import subprocess
import sys

import pytest

# The code under test lives in the payload dir; these tests deliberately do not, so that nothing test-shaped is
# copied onto a Processor when the payload ships (section 4.4 of MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'payload', 'fn-nrvv', 'src'))


def git(cwd, *args):
    r = subprocess.run(['git', '-c', 'user.name=test', '-c', 'user.email=test@example.com', *args],
                       cwd=cwd, capture_output=True, text=True, encoding='utf-8', check=False)
    assert r.returncode == 0, 'git ' + ' '.join(args) + ': ' + r.stderr
    return r.stdout.strip()


def write(root, files):
    for rel, content in files.items():
        p = os.path.join(root, *rel.split('/'))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)


class GitWorld:
    """A bare 'remote' repository with a branch `main`, built under the test's own tmp_path, plus the seed working
    copy that pushes to it. Everything a test checks out comes from here - never from a real repository."""

    def __init__(self, tmp_path):
        self.seed = str(tmp_path / 'seed')
        self.bare = str(tmp_path / 'remote.git')

    @property
    def url(self):
        return self.bare

    def init(self, files):
        os.makedirs(self.seed)
        git(self.seed, 'init', '-q', '-b', 'main')
        write(self.seed, files)
        git(self.seed, 'add', '-A')
        git(self.seed, 'commit', '-q', '-m', 'initial')
        git(os.path.dirname(self.seed), 'clone', '-q', '--bare', self.seed, self.bare)
        git(self.seed, 'remote', 'add', 'origin', self.bare)
        return git(self.seed, 'rev-parse', 'HEAD')

    def push_change(self, files):
        write(self.seed, files)
        git(self.seed, 'add', '-A')
        git(self.seed, 'commit', '-q', '-m', 'change')
        git(self.seed, 'push', '-q', 'origin', 'main')
        return git(self.seed, 'rev-parse', 'HEAD')

    def tip(self, branch='main'):
        return git(self.bare, 'rev-parse', branch)


@pytest.fixture
def world(tmp_path):
    return GitWorld(tmp_path)
