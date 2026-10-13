# mh.asset.nrvv-cv-need-contradiction-prompt_1.0 - the CONTRADICTION NEED-check prompt (plan 047, Phase 10).
#
# Inputs  (process metas variable-for-<role>):
#   agreed-needs   the agreed NEEDs at the run's snapshot, with their clause kinds (mhdg-nrvv.read-agreed-needs)
# Output:
#   prompt         the prompt for mh.asset.call-cc_1.2

import sys

import mh_task_io as io
import nrvv_cv_need as cv
import nrvv_cv_need_contradiction as wf

FUNCTION_CODE = 'mh.asset.nrvv-cv-need-contradiction-prompt_1.0'


def main(argv):
    cv.run_prompt(io.load_params(argv)['task'], FUNCTION_CODE, wf.compose)


if __name__ == '__main__':
    main(sys.argv)
