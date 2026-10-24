# mh.asset.nrvv-concept-terms-prompt_1.0 - the CC prompt listing the load-bearing terms of an expectation and its NEEDs, with candidate readings (plan 050 decision 10).
#
# Inputs  (process metas variable-for-<role>):
#   concept-input  {"expectation", "needs": [{"reqId", "kind", "title", "statement"}]}
# Output:
#   prompt         the prompt for the terms session (mh.asset.call-cc_1.2)

import sys

import mh_task_io as io
import nrvv_concept as wf

FUNCTION_CODE = 'mh.asset.nrvv-concept-terms-prompt_1.0'


def main(argv):
    wf.run_terms_prompt(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
