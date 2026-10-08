# mh.asset.nrvv-assessment-check_1.0 - check CC's NEED-assessment answer and hand it on in canonical form (plan 045,
# Phase 7).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result     CC's answer, stored through call-cc's result tool: {"findings": [...]}
#   agreed-needs  the agreed NEEDs the prompt listed - a counterpart must be one of them
# Output:
#   findings      {"findings": [{"kind", "counterpart"?, "text"}]}, what mhdg-nrvv.store-findings stores
#
# Refuses (the Task fails, so finish-run ends the run ERROR and nothing is stored): not JSON (one markdown fence is
# unwrapped, nothing else), not {"findings": [...]}, an unknown kind, an unknown field, a blank text, a pair finding
# without a counterpart, a counterpart that is not an agreed NEED. The Dispatcher checks the same again.
#
# Pure but for run()/main().

import json
import sys

import mh_task_io as io
import nrvv_assessment as na

FUNCTION_CODE = 'mh.asset.nrvv-assessment-check_1.0'


def run(task):
    needs = na.agreed_needs_of(io.read_role(task, 'agreed-needs'))
    answer = na.findings_of(io.read_role(task, 'cc-result'), needs)
    io.write_text(io.output_role(task, 'findings'), json.dumps(answer, ensure_ascii=False))
    print(FUNCTION_CODE + ': ' + str(len(answer['findings'])) + ' finding(s): '
          + ', '.join(f['kind'] + ('/' + f['counterpart'] if 'counterpart' in f else '') for f in answer['findings']))


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
