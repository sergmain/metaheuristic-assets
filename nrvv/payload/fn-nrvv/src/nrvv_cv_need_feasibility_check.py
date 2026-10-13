# mh.asset.nrvv-cv-need-feasibility-check_1.0 - check CC's FEASIBILITY verdict and hand it on in canonical form
# (plan 047, Phase 11).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result      CC's answer, stored through call-cc's result tool: {"verdict": ...}
#   agreed-needs   the NEEDs the prompt listed - the INFEASIBLE set is a subset of them, a witness names every one
# Output:
#   findings       the canonical verdict (nrvv_cv_need_feasibility.verdict_of) - what mhdg-nrvv.store-findings turns
#                  into a finding (INFEASIBLE, UNDERDETERMINED) or none (DETERMINED)
#
# Refuses (the Task fails, so finish-run ends the run ERROR and nothing is stored): not JSON, an unknown field or
# verdict, an INFEASIBLE set that is empty, repeats or names an unknown NEED, an INFEASIBLE without a reason, a witness
# missing, over 2000 characters or not naming every agreed NEED, an UNDERDETERMINED without open choices. The Dispatcher
# checks the same again.

import sys

import mh_task_io as io
import nrvv_cv_need_feasibility as wf

FUNCTION_CODE = 'mh.asset.nrvv-cv-need-feasibility-check_1.0'


def main(argv):
    wf.run_check(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
