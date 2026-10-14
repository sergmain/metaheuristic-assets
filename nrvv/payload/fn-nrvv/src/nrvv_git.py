# Git, through the git CLI, for the NRVV Functions: resolve a ref, check out a commit, list what changed, commit,
# push. Every call runs `git` as a subprocess and fails loudly with git's own stderr.
#
# Plan 047 Phase 26 (decision 19): a network-class failure - exit 128 with `Could not resolve host`, `Connection timed
# out` or `unable to access` - is retried, RETRY_DELAYS apart (5 retries, 10/20/30/30/30 s); every other failure, and
# the last retry's, fails at once as before.

import os
import re
import subprocess
import sys
import time

SHA = re.compile(r'^[0-9a-f]{40}$')
# git's refusal of a push whose branch moved since the checkout: the remote holds commits this checkout does not have
REJECTED_BEHIND = re.compile(r'\[rejected\][^\n]*\((?:fetch first|non-fast-forward)\)')
# plan 047 Phase 26: git could not reach the host - the same command may succeed a moment later
NETWORK_FAILURE = re.compile(r'Could not resolve host|Connection timed out|unable to access')
RETRY_DELAYS = (10, 20, 30, 30, 30)


class GitError(RuntimeError):
    pass


def is_network_failure(returncode, output):
    """True for git's exit 128 with a message naming a host it could not resolve or reach."""
    return returncode == 128 and bool(NETWORK_FAILURE.search(output or ''))


def git(args, cwd=None, extra_config=None, env_config=None, strip=True, run=subprocess.run, sleep=time.sleep):
    """Run one git command; return stdout, stripped unless strip=False.

    strip=False is required for -z output: porcelain entries begin with a status column that may be a space
    (' M path'), and stripping the whole output eats that space from the FIRST entry and shifts its path.

    extra_config: 'key=value' items passed as -c - on the command line, so never for a secret.
    env_config: (key, value) pairs passed through GIT_CONFIG_COUNT / GIT_CONFIG_KEY_n / GIT_CONFIG_VALUE_n in the
    child's environment only - readable by the same OS user, not by every process listing argv.

    run / sleep: how the command runs and how a retry waits - subprocess.run and time.sleep; a network-class failure
    (is_network_failure) is run again after each of RETRY_DELAYS."""
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
    attempt = 0
    while True:
        r = run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding='utf-8', check=False)
        attempt += 1
        if r.returncode == 0:
            return r.stdout.strip() if strip else r.stdout
        output = (r.stderr or r.stdout or '').strip()
        if attempt <= len(RETRY_DELAYS) and is_network_failure(r.returncode, output):
            delay = RETRY_DELAYS[attempt - 1]
            print('nrvv_git: git ' + (args[0] if args else '') + ' failed with a network error on attempt '
                  + str(attempt) + ', retried in ' + str(delay) + ' s: ' + output, file=sys.stderr)
            sleep(delay)
            continue
        raise GitError('git ' + ' '.join(args) + ' failed with exit ' + str(r.returncode)
                       + (' after ' + str(attempt) + ' attempts' if attempt > 1 else '') + ': ' + output)


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


DEEPEN_BY = 50
DEEPEN_ROUNDS = 20


def shallow_commits(repo_root):
    """The boundary commits of a shallow repository (.git/shallow) - their parents are not fetched; empty when complete."""
    path = os.path.join(repo_root, '.git', 'shallow')
    if not os.path.isfile(path):
        return set()
    with open(path, encoding='utf-8') as f:
        return {line.strip() for line in f if line.strip()}


def newest_commit_touching(repo_root, rev, rel_dir, url=None, branch=None, auth_header=None):
    """Plan 047 Phase 24 (decision 18): the newest commit at or before `rev` touching `rel_dir` (repository-relative,
    '/'-separated); `rev` itself for no dir or when no commit touches it.

    A checkout is fetched one commit deep, and a shallow boundary commit looks as if it added every file - so a commit
    found on the boundary is no answer yet: the branch is deepened by DEEPEN_BY commits (from `url`, with the same
    auth header as the push) and asked again, until the commit found lies inside the fetched history, the history is
    complete, or DEEPEN_ROUNDS rounds were fetched. Call it after run_commits(): deepening ends the one-commit history
    that run_commits relies on."""
    d = (rel_dir or '').strip().strip('/')
    if not d:
        return rev
    env_config = [('http.extraHeader', auth_header)] if auth_header else None
    sha = ''
    for _ in range(DEEPEN_ROUNDS):
        sha = git(['log', '-1', '--format=%H', rev, '--', d], cwd=repo_root)
        boundary = shallow_commits(repo_root)
        if not boundary or (sha and sha not in boundary) or url is None or branch is None:
            break
        git(['fetch', '-q', '--deepen', str(DEEPEN_BY), url, 'refs/heads/' + branch], cwd=repo_root, env_config=env_config)
    return sha or rev


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


def run_commits(repo_root):
    """The commits made on top of the checkout, oldest first. checkout() fetches its commit one commit deep, so HEAD's
    history ends at that commit; it is excluded. Empty when nothing was committed since the checkout."""
    return git(['rev-list', '--reverse', 'HEAD'], cwd=repo_root).split()[1:]


def push_onto_moving_branch(repo_root, url, branch, committer_name, committer_email, auth_header=None, attempts=3):
    """Push the run's commits (run_commits) to refs/heads/<branch> on url, on top of whatever the branch holds by then;
    return the sha pushed (plan 043, Phase 7).

    Runs and the executor push to the same branch, so the branch can move between a run's checkout and its push. A
    push git refuses for that reason ('[rejected] ... (fetch first)' / '(non-fast-forward)') fetches the branch tip one
    commit deep, cherry-picks the run's commits onto it and pushes again - at most `attempts` pushes. A cherry-pick
    that conflicts fails with git's own message, and so does a push refused for any other reason, at once."""
    commits = run_commits(repo_root)
    env_config = [('http.extraHeader', auth_header)] if auth_header else None
    for attempt in range(1, attempts + 1):
        try:
            git(['push', '-q', url, 'HEAD:refs/heads/' + branch], cwd=repo_root, env_config=env_config)
            return head(repo_root)
        except GitError as e:
            if attempt == attempts or not commits or not REJECTED_BEHIND.search(str(e)):
                raise
        git(['fetch', '-q', '--depth', '1', url, 'refs/heads/' + branch], cwd=repo_root, env_config=env_config)
        git(['checkout', '-q', '-f', '--detach', 'FETCH_HEAD'], cwd=repo_root)
        _cherry_pick(repo_root, commits, branch, committer_name, committer_email)
    raise GitError('push to ' + branch + ' did not land after ' + str(attempts) + ' attempts')


def _cherry_pick(repo_root, commits, branch, committer_name, committer_email):
    """Replay `commits` onto HEAD. On failure the cherry-pick is aborted and git's own report is raised - stdout too,
    where git writes the CONFLICT lines."""
    r = subprocess.run(['git', '-c', 'user.name=' + committer_name, '-c', 'user.email=' + committer_email,
                        'cherry-pick', *commits],
                       cwd=repo_root, capture_output=True, text=True, encoding='utf-8', check=False)
    if r.returncode != 0:
        subprocess.run(['git', 'cherry-pick', '--abort'], cwd=repo_root, capture_output=True, check=False)
        raise GitError('git cherry-pick of ' + str(len(commits)) + ' commit(s) onto the tip of ' + branch
                       + ' failed with exit ' + str(r.returncode) + ': ' + (r.stdout + '\n' + r.stderr).strip())
