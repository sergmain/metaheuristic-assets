# mh.asset.nrvv-cv-need-backtrace-prompt_1.0 - the BACKTRACE (back-validation) prompt for one chunk of subjects
# (plan 047, Phase 17). CC answers through call-cc's result tool; mh.asset.nrvv-cv-need-backtrace-check_1.0 checks it.
#
# Inputs  (process metas variable-for-<role>):
#   backtrace-context   the agreed NEEDs and every subject at the run's snapshot (mhdg-nrvv.read-backtrace-input)
#   subjects            this chunk's subjects, one reqId per line (mh.batch-line-splitter over read-backtrace-input's
#                       `subjects`)
# Output:
#   prompt              the prompt for mh.asset.call-cc_1.2

import sys

import mh_task_io as io
import nrvv_cv_need_backtrace as wf

FUNCTION_CODE = 'mh.asset.nrvv-cv-need-backtrace-prompt_1.0'


def main(argv):
    wf.run_prompt(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
