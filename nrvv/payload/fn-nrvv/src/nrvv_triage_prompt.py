# mh.asset.nrvv-triage-prompt_1.0 - the TRIAGE prompt (plan 047, Phase 23).
#
# Inputs  (process metas variable-for-<role>):
#   triage-context   the tests that did not pass, their suites' requirements and criteria, the requirements in force
#                    (NrvvTriageService, input triageContext)
#   test-suite-dir   the absolute test-suite dir of the checkout (mh.asset.nrvv-checkout_1.0's dir-path)
# Output:
#   prompt           the prompt for mh.asset.call-cc_1.2: the tests, their files, the suites, tests/nrvv_env/ when present

import sys

import mh_task_io as io
import nrvv_triage as tr

FUNCTION_CODE = 'mh.asset.nrvv-triage-prompt_1.0'


def main(argv):
    tr.run_prompt(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)