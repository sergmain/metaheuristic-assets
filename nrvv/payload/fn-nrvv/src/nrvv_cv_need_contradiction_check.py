# mh.asset.nrvv-cv-need-contradiction-check_1.0 - check CC's CONTRADICTION findings and hand them on in canonical form
# (plan 047, Phase 10).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result      CC's answer, stored through call-cc's result tool: {"findings": [...]}
#   agreed-needs   the NEEDs the prompt listed - a subject and its counterpart must be two of them
# Output:
#   findings       {"findings": [{"kind": "CONTRADICTION", "subject", "counterpart", "text"}]}, a mirrored pair once
#
# Refuses (the Task fails, so finish-run ends the run ERROR and nothing is stored): not JSON, not {"findings": [...]},
# a kind other than CONTRADICTION, an unknown field, a blank text, a subject that is not an agreed NEED, no other agreed
# NEED as counterpart. The Dispatcher checks the same again.

import sys

import mh_task_io as io
import nrvv_cv_need as cv
import nrvv_cv_need_contradiction as wf

FUNCTION_CODE = 'mh.asset.nrvv-cv-need-contradiction-check_1.0'


def main(argv):
    cv.run_check(io.load_params(argv)['task'], FUNCTION_CODE, wf.KINDS, wf.PAIR_KINDS)


if __name__ == '__main__':
    main(sys.argv)
