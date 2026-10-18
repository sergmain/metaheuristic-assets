# mh.asset.nrvv-cv-req-local-prompt_1.0 - the LOCAL_CONTRADICTION prompt for one requirement and its candidates. CC
# answers through call-cc's result tool; mh.asset.nrvv-cv-req-local-check_1.0 checks it.
#
# Inputs  (process metas variable-for-<role>):
#   local-cv-context  per subject its text and its candidates with why and text (mhdg-nrvv.read-local-cv-input)
#   subjects          this chunk's subject, one reqId (mh.batch-line-splitter over read-local-cv-input's `subjects`)
# Output:
#   prompt            the prompt for mh.asset.call-cc_1.2

import sys

import mh_task_io as io
import nrvv_cv_req_local as wf

FUNCTION_CODE = 'mh.asset.nrvv-cv-req-local-prompt_1.0'


def main(argv):
    wf.run_prompt(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
