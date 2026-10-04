# Git, through the git CLI, for the NRVV Functions: resolve a ref, check out a commit, list what changed, commit,
# push. Every call runs `git` as a subprocess and fails loudly with git's own stderr.

import os
import re
import subprocess

SHA = re.compile(r'^[0-9a-f]{40}$')


class GitError(RuntimeError):
    pass


def git(args, cwd=None, extra_config=None, env_config=None, strip=True):
    """Run one git command; return stdout, stripped unless strip=False.

    strip=False is required for -z output: porcelain entries begin with a status column that may be a space
    (' M path'), and stripping the whole output eats that space from the FIRST entry and shifts its path.

    extra_config: 'key=value' items passed as -c - on the command line, so never for a secret.
    env_config: (key, value) pairs passed through GIT_CONFIG_COUNT / GIT_CONFIG_KEY_n / GIT_CONFIG_VALUE_n in the
    child's environment only - readable by the same OS user, not by every process listing argv."""
    cmd = ['git']
    for kv in extra_config or []:
        cmd += ['-c', kv]
    cmd += list(args)
    env = None
    if env_config:
        env = dict(os.environ)
        env['GIT_CONFIG_COUNT'] = str(len(env_config))
        for i, (k, v) in enumerate(env_config):
            env['GIT_CONFIG_KEY_' + str(i)] = k
            env['GIT_CONFIG_VALUE_' + str(i)] = v
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding='utf-8', check=False)
    if r.returncode != 0:
        raise GitError('git ' + ' '.join(args) + ' failed with exit ' + str(r.returncode) + ': '
                       + (r.stderr or r.stdout).strip())
    return r.stdout.strip() if strip else r.stdout


def resolve_ref(url, ref):
    """The commit sha a ref names on the remote. A full sha is its own answer; otherwise a branch, then a tag
    (peeled to its commit), then HEAD."""
    if SHA.match(ref or ''):
        return ref
    out = git(['ls-remote', url])
    refs = {}
    for line in out.splitlines():
        if '\t' in line:
            sha, name = line.split('\t', 1)
            refs[name] = sha
    for name in ('refs/heads/' + ref, 'refs/tags/' + ref + '^{}', 'refs/tags/' + ref, ref):
        if name in refs:
            return refs[name]
    raise GitError("ref '" + str(ref) + "' not found on " + url)


def head(repo_root):
    return git(['rev-parse', 'HEAD'], cwd=repo_root)


def is_clean(repo_root):
    return git(['status', '--porcelain=v1', '-uall'], cwd=repo_root) == ''


def checkout(url, ref, repo_root):
    """Bring repo_root to exactly the commit `ref` names on `url`, and return that sha.

    Idempotent by commit sha: a checkout already at that sha with a clean tree is left untouched. Anything else -
    no checkout yet, another sha, a dirty tree from a failed attempt - is fetched (one commit deep) and forced to
    the sha, with untracked files removed, so a re-run always starts from the commit and nothing else."""
    sha = resolve_ref(url, ref)
    if os.path.isdir(os.path.join(repo_root, '.git')):
        if head(repo_root) == sha and is_clean(repo_root):
            return sha
    else:
        os.makedirs(repo_root, exist_ok=True)
        git(['init', '-q'], cwd=repo_root)
        git(['remote', 'add', 'origin', url], cwd=repo_root)
    git(['fetch', '-q', '--depth', '1', 'origin', sha], cwd=repo_root)
    git(['checkout', '-q', '-f', '--detach', sha], cwd=repo_root)
    git(['clean', '-q', '-fdx'], cwd=repo_root)
    return sha


def _split_z(out):
    return [e for e in out.split('\0') if e]


def changed_paths(repo_root, base_sha):
    """Every repository-relative path that differs from base_sha: committed since it, staged, unstaged or
    untracked. A rename counts both of its paths - moving a file out of a dir changes that dir too."""
    paths = set(_split_z(git(['diff', '--name-only', '--no-renames', '-z', base_sha, 'HEAD'], cwd=repo_root,
                             strip=False)))
    entries = _split_z(git(['status', '--porcelain=v1', '-z', '-uall', '--no-renames'], cwd=repo_root,
                           strip=False))
    for e in entries:
        paths.add(e[3:])
    return sorted(p.replace('\\', '/') for p in paths)


def commit_all(repo_root, message, author_name, author_email):
    """Stage everything and commit it; return the resulting HEAD sha. Nothing to commit returns HEAD unchanged."""
    git(['add', '-A'], cwd=repo_root)
    staged = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=repo_root, check=False).returncode
    if staged == 0:
        return head(repo_root)
    git(['commit', '-q', '-m', message], cwd=repo_root,
        extra_config=['user.name=' + author_name, 'user.email=' + author_email])
    return head(repo_root)


def push(repo_root, url, branch, auth_header=None):
    """Push HEAD to refs/heads/<branch> on url. auth_header, when given, is sent as an HTTP header; it reaches the
    git child through its environment (env_config), never through argv and never through a file."""
    env_config = [('http.extraHeader', auth_header)] if auth_header else None
    git(['push', '-q', url, 'HEAD:refs/heads/' + branch], cwd=repo_root, env_config=env_config)
