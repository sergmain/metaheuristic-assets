# mh.asset.nrvv-cv-need-completeness-prompt_1.0 - the COMPLETENESS prompt for one chunk of derivation NEEDs. CC answers
# through call-cc's result tool; mh.asset.nrvv-cv-need-completeness-check_1.0 checks it.
#
# Inputs  (process metas variable-for-<role>):
#   completeness-context  per NEED: the NEED, its governing items, its top-level requirements
#                         (mhdg-nrvv.read-completeness-input)
#   subjects              this chunk's NEEDs, one reqId per line (mh.batch-line-splitter over read-completeness-input's
#                         `subjects`)
# Output:
#   prompt                the prompt for mh.asset.call-cc_1.2

import sys

import mh_task_io as io
import nrvv_cv_need_completeness as wf

FUNCTION_CODE = 'mh.asset.nrvv-cv-need-completeness-prompt_1.0'


def main(argv):
    wf.run_prompt(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
