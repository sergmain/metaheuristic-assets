# mh.asset.nrvv-triage-check_1.0 - check CC's triage and hand it on in canonical form (plan 047, Phase 23).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result        CC's answer, stored through call-cc's result tool: {"triage": [...]}
#   triage-context   the tests the prompt listed - each is answered exactly once
# Output:
#   triage           the canonical triage (nrvv_triage.classes_of) - what mhdg-nrvv.store-triage records on the run
#
# Refuses (the Task fails, so finish-run ends the run ERROR and nothing is stored): not JSON, an unknown field, a test
# not listed or answered twice, a listed test unanswered, an unknown class, a reason empty, of several lines or over 400
# characters. The Dispatcher checks the same again against the VERIFICATION's results.

import sys

import mh_task_io as io
import nrvv_triage as tr

FUNCTION_CODE = 'mh.asset.nrvv-triage-check_1.0'


def main(argv):
    tr.run_check(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)