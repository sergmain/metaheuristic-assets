# mh.asset.nrvv-concept-readings-check_1.0 - check one readings session's answer (plan 050 decision 10).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result      the session's answer {"readings": [...]}
#   concept-input  what the prompt was built from
#   terms          the canonical terms
#   session        this branch's session number
# Output:
#   readings       {"session", "readings": [{"term", "pick", "quote"?, "why"?}]} on ONE line (mh.aggregate joins by newline)
#
# Refuses a wrong shape; a pick that is no letter of its term, or whose quote is not in the text, is INVALID.

import sys

import mh_task_io as io
import nrvv_concept as wf

FUNCTION_CODE = 'mh.asset.nrvv-concept-readings-check_1.0'


def main(argv):
    wf.run_readings_check(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
