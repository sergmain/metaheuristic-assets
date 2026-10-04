# Where things live inside one NRVV run workspace (plan 042, decision 8).
#
# The workspace itself - ${mh.home}/nrvv/<INFO_BANK>/<nrvvCode>/<snapshotId>/<runId>, or
# ${mh.home}/nrvv/_recovery/<runId> - is computed ONCE, on the Dispatcher side, and handed to every Function of the
# run as an absolute path. A Function cannot compute it: its params file carries no mh.home, only the Task's own
# workingPath, which is removed when the Task is cleaned. Decision 9 (one box) makes the handed path valid for every
# Task. This module only decides what goes UNDER it.
#
#   <workspace>/source/        RECOVERY: the repository the requirements are recovered from
#   <workspace>/test-suite/    the NRVV project's test-suite repository
#   <workspace>/target/        the NRVV project's target repository
#   <workspace>/verification/  the launcher's JUnit XML, one file per suite
#
# Pure: no IO.

import os

ROLES = ('source', 'test-suite', 'target')
VERIFICATION = 'verification'


def require_workspace(workspace):
    """The workspace must be absolute: it is shared by every Task of the run, whatever directory each runs in."""
    if not workspace or not os.path.isabs(workspace):
        raise ValueError("workspace must be an absolute path, actual: '" + str(workspace) + "'")
    return os.path.normpath(workspace)


def checkout_root(workspace, role):
    """The repository root of one role's checkout."""
    if role not in ROLES:
        raise ValueError("role must be one of " + str(list(ROLES)) + ", actual: '" + str(role) + "'")
    return os.path.join(require_workspace(workspace), role)


def rel_parts(rel_dir):
    """The parts of a repository-relative dir. Empty means the repository root. An absolute dir, a drive, or a
    '..' would point outside the checkout, and is refused rather than normalized away."""
    raw = rel_dir or ''
    if raw.startswith(('/', '\\')) or ':' in raw:
        raise ValueError("dir must be repository-relative, actual: '" + raw + "'")
    parts = [p for p in raw.replace('\\', '/').split('/') if p not in ('', '.')]
    if '..' in parts:
        raise ValueError("dir must not contain '..', actual: '" + raw + "'")
    return parts


def dir_path(workspace, role, rel_dir):
    """The absolute path of a repository-relative dir inside one role's checkout."""
    return os.path.join(checkout_root(workspace, role), *rel_parts(rel_dir))


def rel_posix(rel_dir):
    """The repository-relative dir in git's own spelling: forward slashes, no leading or trailing slash."""
    return '/'.join(rel_parts(rel_dir))


def verification_dir(workspace):
    return os.path.join(require_workspace(workspace), VERIFICATION)
