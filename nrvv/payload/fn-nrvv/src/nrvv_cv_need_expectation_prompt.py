# mh.asset.nrvv-cv-need-expectation-prompt_1.0 - the EXPECTATION NEED-check prompt for one chunk (plan 048, Phase 5).
#
# Inputs  (process metas variable-for-<role>):
#   agreed-needs   the agreed NEEDs at the run's snapshot, each with its clause (mhdg-nrvv.read-agreed-needs)
#   subjects       this chunk's NEEDs, one reqId per line - each an agreed NEED with a clause
# Output:
#   prompt         the prompt for mh.asset.call-cc_1.2

import sys

import mh_task_io as io
import nrvv_cv_need_expectation as wf

FUNCTION_CODE = 'mh.asset.nrvv-cv-need-expectation-prompt_1.0'


def main(argv):
    wf.run_prompt(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
