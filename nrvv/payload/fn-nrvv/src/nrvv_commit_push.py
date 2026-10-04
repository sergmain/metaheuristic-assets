# mh.asset.nrvv-commit-push_1.0 - commit everything in one role's checkout and push it to the location's branch.
#
# Inputs:
#   workspace       absolute path of the run workspace
#   location        JSON {"url", "branchOrRef", "dir"} - pushed to refs/heads/<branchOrRef> on url
#   commit-message  the commit message
# Meta:
#   nrvv-role       the checkout to commit (test-suite or target)
# Output:
#   commit          the sha now at the branch tip (unchanged when there was nothing to commit)
#
# Credential: api.keyCode NRVV_GIT_AUTH. The Vault entry holds `user:token`; it arrives over the Processor's loopback
# secret channel and is sent as an HTTP Basic header through the git child's environment - never argv, never disk.
# Without a handoff (no api key declared, a local remote) the push goes out with no header.

import base64
import sys

import mh_secret_client as secret
import mh_task_io as io
import nrvv_checkout
import nrvv_git
import nrvv_paths

AUTHOR_NAME = 'nrvv'
AUTHOR_EMAIL = 'nrvv@metaheuristic.local'


def basic_auth_header(user_colon_token):
    """'Authorization: Basic <base64(user:token)>' for a Vault value of the form user:token."""
    if ':' not in user_colon_token:
        raise ValueError('the git credential must have the form user:token')
    return 'Authorization: Basic ' + base64.b64encode(user_colon_token.encode('utf-8')).decode('ascii')


def commit_and_push(repo_root, location, message, auth_header=None):
    """The sha at the branch tip after committing every change and pushing it."""
    sha = nrvv_git.commit_all(repo_root, message, AUTHOR_NAME, AUTHOR_EMAIL)
    nrvv_git.push(repo_root, location['url'], location['branchOrRef'], auth_header)
    return sha


def main(argv):
    params = io.load_params(argv)
    task = params['task']
    role = io.require_meta(task.get('metas') or [], 'nrvv-role')
    workspace = io.read_role(task, 'workspace').strip()
    location = nrvv_checkout.parse_location(io.read_role(task, 'location'))
    message = (io.read_role(task, 'commit-message') or '').strip() or 'nrvv'

    header = None
    port, code = secret.extract_secret_fields(params)
    if port is not None:
        key = secret.exchange(port, code)
        try:
            header = basic_auth_header(key.decode('utf-8'))
        finally:
            secret.zero(key)

    sha = commit_and_push(nrvv_paths.checkout_root(workspace, role), location, message, header)
    io.write_text(io.output_role(task, 'commit'), sha)
    print('nrvv-commit-push: ' + role + ' -> ' + location['branchOrRef'] + ' @ ' + sha)


if __name__ == '__main__':
    main(sys.argv)
