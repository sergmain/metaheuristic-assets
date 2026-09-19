# mh.asset.rg-req-check_1.0 - check ONE file's CC answer inside that file's branch, and hand it on as one line.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# rg-requirements/functions/fn-rg-req-check/mh-function.yaml.
#
# roles - every Variable is named by a meta, never hard-coded:
#   source-path   INPUT  - the file the answer is about: the branch's line
#   cc-result     INPUT  - CC's answer: a JSON array of {name, content, rationale}
#   answer        OUTPUT - ONE line of JSON: {"sourcePath": ..., "requirements": [{name, content, rationale}]}
#
# WHY IN THE BRANCH. Nothing is stored in a branch - see mh.asset.rg-req-store-batch_1.0 - so every answer
# travels to one store Task. Checking it where it was produced makes a bad answer fail ITS branch, visible at
# that file and repaired by resetting that branch's cc Task, rather than failing the one Task that holds every
# file's work. The check is mh.asset.rg-req-store_1.0's own parse_requirements, so an answer that passes here
# is one the store accepts.
#
# ONE LINE, ASCII. internal mh.aggregate (type text) joins the branches' answers with a blank line. json.dumps
# escapes every newline inside a string, and with ensure_ascii every non-ASCII character too - U+2028 among
# them, which str.splitlines would otherwise read as a line break - so each answer is exactly one line whatever
# the requirements say, and the store takes the collection apart line by line.

import json
import sys

from mh_rg_req_path_prompt import the_path
from mh_rg_req_store import parse_requirements
from mh_task_io import load_params, output_role, read_role, write_text

FUNCTION_CODE = 'mh.asset.rg-req-check_1.0'


def answer_line(source_path, cc_result):
    """The checked answer as one line of ASCII JSON, or the failure parse_requirements raises."""
    path = the_path(source_path)
    requirements = parse_requirements(cc_result)
    return json.dumps({'sourcePath': path, 'requirements': requirements}, ensure_ascii=True)


def main(argv):
    print(FUNCTION_CODE)
    params = load_params(argv)
    task = params['task']
    try:
        line = answer_line(read_role(task, 'source-path'), read_role(task, 'cc-result'))
        write_text(output_role(task, 'answer'), line)
        answer = json.loads(line)
        print(answer['sourcePath'] + ': ' + str(len(answer['requirements'])) + ' requirement(s)')
        return 0
    except (ValueError, OSError) as e:
        print('FAILED: ' + str(e))
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
