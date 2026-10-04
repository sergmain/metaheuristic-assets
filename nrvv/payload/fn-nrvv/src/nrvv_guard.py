# mh.asset.nrvv-guard_1.0 - fail the Task when any change in a checkout lies outside the one dir a session was
# allowed to write (plan 042, decision 17: a path check, not trust).
#
# Inputs:
#   workspace     absolute path of the run workspace
#   location      JSON {"url", "branchOrRef", "dir"} - `dir` is the allowed dir
#   base-commit   the sha the checkout started from (nrvv-checkout's `commit`)
# Meta:
#   nrvv-role     the checkout to inspect (target for the implementation run)
# Output:
#   guard-report  the changed paths, one per line; written only when the guard passes
#
# "Changed" is everything that differs from base-commit: committed since it, staged, unstaged, untracked; a rename
# counts both paths. An empty allowed dir (the repository root) allows everything.

import sys

import mh_task_io as io
import nrvv_checkout
import nrvv_git
import nrvv_paths


class GuardError(RuntimeError):
    pass


def paths_outside(paths, allowed_rel_dir):
    """The paths not under allowed_rel_dir (forward slashes, repository-relative). Pure."""
    allowed = nrvv_paths.rel_posix(allowed_rel_dir)
    if not allowed:
        return []
    return [p for p in paths if p != allowed and not p.startswith(allowed + '/')]


def check(repo_root, base_sha, allowed_rel_dir):
    """The changed paths when every one lies under allowed_rel_dir; GuardError naming the offenders otherwise."""
    changed = nrvv_git.changed_paths(repo_root, base_sha)
    outside = paths_outside(changed, allowed_rel_dir)
    if outside:
        raise GuardError('changes outside the allowed dir \'' + nrvv_paths.rel_posix(allowed_rel_dir) + '\': '
                         + ', '.join(outside))
    return changed


def main(argv):
    task = io.load_params(argv)['task']
    role = io.require_meta(task.get('metas') or [], 'nrvv-role')
    workspace = io.read_role(task, 'workspace').strip()
    location = nrvv_checkout.parse_location(io.read_role(task, 'location'))
    base = io.read_role(task, 'base-commit').strip()
    changed = check(nrvv_paths.checkout_root(workspace, role), base, location['dir'])
    io.write_text(io.output_role(task, 'guard-report'), '\n'.join(changed))
    print('nrvv-guard: ' + str(len(changed)) + ' changed path(s), all under \'' + location['dir'] + '\'')


if __name__ == '__main__':
    main(sys.argv)
