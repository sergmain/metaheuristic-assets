# mh.asset.nrvv-wording-check_1.0 - check CC's NEED-wording answer and hand it on in canonical form (plan 045,
# Phase 8).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result   CC's answer, stored through call-cc's result tool: {"title", "statement"}
# Output:
#   wording     {"title", "statement"}, both stripped - what mhdg-nrvv.finish-run records as the run's suggestion
#
# Refuses (the Task fails, so finish-run ends the run ERROR and no suggestion is recorded): not JSON (one markdown
# fence is unwrapped, nothing else), not an object, an unknown field, a missing or blank title or statement, a title
# that is not one line or is longer than 250 characters. The Dispatcher checks the same again.
#
# Pure but for run()/main().

import json
import sys

import mh_task_io as io
import nrvv_wording as nw

FUNCTION_CODE = 'mh.asset.nrvv-wording-check_1.0'


def run(task):
    answer = nw.wording_of(io.read_role(task, 'cc-result'))
    io.write_text(io.output_role(task, 'wording'), json.dumps(answer, ensure_ascii=False))
    print(FUNCTION_CODE + ': title ' + repr(answer['title']) + ', statement ' + str(len(answer['statement'])) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
