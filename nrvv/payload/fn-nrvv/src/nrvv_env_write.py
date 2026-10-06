# mh.asset.nrvv-env-write_1.0 - check CC's nrvv_env answer and write it as <test-suite dir>/tests/nrvv_env/ (plan 043,
# Phase 9). See nrvv_environment.py.
#
# Inputs  (process metas variable-for-<role>):
#   workspace   absolute path of the run workspace
#   location    the NRVV project's test-suite location, JSON {"url", "branchOrRef", "dir"} - checked out before
#   cc-result   CC's answer, stored through call-cc's result tool: {"files": {"<module>.py": "<content>"}}
# Output:
#   files       JSON array of the repository-relative paths written
#
# THE CHECKS, all before anything is written: the answer is one JSON object with a non-empty "files" map; every name is
# __init__.py or a lowercase module name ending in .py, none a file pytest would collect (test_*.py, *_test.py); every
# file parses; every import is the standard library or nrvv_env, never threading, _thread, multiprocessing, asyncio,
# concurrent, time, socket or subprocess. Then tests/nrvv_env/ is REPLACED - a re-run's package never mixes with an
# earlier one's - and an empty __init__.py added when the answer has none.
#
# Pure but for run()/main() and nrvv_environment.write_env().

import json
import os
import sys

import mh_task_io as io
import nrvv_environment as ne
import nrvv_paths
from nrvv_checkout import parse_location

FUNCTION_CODE = 'mh.asset.nrvv-env-write_1.0'


def run(task):
    workspace = nrvv_paths.require_workspace((io.read_role(task, 'workspace') or '').strip())
    location = parse_location(io.read_role(task, 'location'))
    files = ne.parse_env_answer(io.read_role(task, 'cc-result'))
    base = nrvv_paths.dir_path(workspace, 'test-suite', location['dir'])
    if not os.path.isdir(base):
        raise ValueError('the test-suite dir does not exist - was it checked out? ' + base)
    written = ne.write_env(base, nrvv_paths.rel_posix(location['dir']), files)
    io.write_text(io.output_role(task, 'files'), json.dumps(written, ensure_ascii=True))
    print(FUNCTION_CODE + ': ' + ', '.join(written))


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
