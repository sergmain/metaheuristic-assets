# mh.asset.nrvv-needs-cv-check_1.0 - check CC's needs-CV answer and hand it on in canonical form (plan 045, Phase 9).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result   CC's answer, stored through call-cc's result tool: {"findings": [...]}
#   trace       the trace the prompt listed - a subject must be one of its NEEDs, a counterpart another NEED or a
#               requirement the subject traces to
# Output:
#   findings    {"findings": [{"kind", "subject", "counterpart"?, "text"}]}, what mhdg-nrvv.store-findings stores
#
# Refuses (the Task fails, so finish-run ends the run ERROR and nothing is stored): not JSON (one markdown fence is
# unwrapped, nothing else), not {"findings": [...]}, an unknown kind (ASSUMPTION included - NRVV writes those), an
# unknown field, a blank text, a subject that is not an agreed NEED, a counterpart that breaks its kind's rule. The
# Dispatcher checks the same again.
#
# Pure but for run()/main().

import json
import sys

import mh_task_io as io
import nrvv_needs_cv as cv

FUNCTION_CODE = 'mh.asset.nrvv-needs-cv-check_1.0'


def run(task):
    trace = cv.trace_of(io.read_role(task, 'trace'))
    answer = cv.findings_of(io.read_role(task, 'cc-result'), trace)
    io.write_text(io.output_role(task, 'findings'), json.dumps(answer, ensure_ascii=False))
    print(FUNCTION_CODE + ': ' + str(len(answer['findings'])) + ' finding(s): '
          + ', '.join(f['kind'] + '/' + f['subject'] + ('/' + f['counterpart'] if 'counterpart' in f else '')
                      for f in answer['findings']))


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
