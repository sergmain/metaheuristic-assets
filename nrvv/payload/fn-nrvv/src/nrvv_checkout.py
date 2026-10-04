# mh.asset.nrvv-checkout_1.0 - bring one role's checkout in the run workspace to the commit a location names.
#
# Inputs  (process metas variable-for-<role>):
#   workspace   absolute path of the run workspace (computed by the Dispatcher, decision 8)
#   location    JSON {"url": ..., "branchOrRef": ..., "dir": ...}  - the same shape as NrvvData.RepoLocation
# Meta:
#   nrvv-role   source | test-suite | target   - which checkout under the workspace
# Outputs:
#   commit      the resolved 40-char commit sha
#   dir-path    the absolute path of `dir` inside the checkout
#
# Idempotent by commit sha (nrvv_git.checkout).

import json
import sys

import mh_task_io as io
import nrvv_git
import nrvv_paths


def parse_location(text):
    """{url, branchOrRef, dir} from JSON; url and branchOrRef are required, dir may be empty (repository root)."""
    if text is None or not text.strip():
        raise ValueError('location is required')
    loc = json.loads(text)
    if not isinstance(loc, dict):
        raise ValueError('location must be a JSON object, actual: ' + text)
    for key in ('url', 'branchOrRef'):
        if not isinstance(loc.get(key), str) or not loc[key].strip():
            raise ValueError("location." + key + " is required, actual: " + text)
    loc.setdefault('dir', '')
    if loc['dir'] is None:
        loc['dir'] = ''
    nrvv_paths.rel_parts(loc['dir'])   # refuses an absolute dir or '..' before anything touches the disk
    return loc


def checkout(workspace, role, location):
    """(sha, absolute dir path) of `location` checked out as `role` under `workspace`."""
    root = nrvv_paths.checkout_root(workspace, role)
    sha = nrvv_git.checkout(location['url'], location['branchOrRef'], root)
    return sha, nrvv_paths.dir_path(workspace, role, location['dir'])


def main(argv):
    task = io.load_params(argv)['task']
    role = io.require_meta(task.get('metas') or [], 'nrvv-role')
    workspace = io.read_role(task, 'workspace').strip()
    location = parse_location(io.read_role(task, 'location'))
    sha, path = checkout(workspace, role, location)
    io.write_text(io.output_role(task, 'commit'), sha)
    io.write_text(io.output_role(task, 'dir-path'), path)
    print('nrvv-checkout: ' + role + ' ' + location['url'] + ' ' + location['branchOrRef'] + ' -> ' + sha)


if __name__ == '__main__':
    main(sys.argv)
