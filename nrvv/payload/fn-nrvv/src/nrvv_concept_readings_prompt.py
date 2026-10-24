# mh.asset.nrvv-concept-readings-prompt_1.0 - the CC prompt of one blind readings session: pick per term the reading the text supports, or OPEN (plan 050 decision 10).
#
# Inputs  (process metas variable-for-<role>):
#   concept-input  {"expectation", "needs": [...]}
#   terms          the canonical terms
#   session        this branch's session number (the splitter's chunk)
# Output:
#   prompt         the readings prompt of the session - readings listed in an order rotated by the session number

import sys

import mh_task_io as io
import nrvv_concept as wf

FUNCTION_CODE = 'mh.asset.nrvv-concept-readings-prompt_1.0'


def main(argv):
    wf.run_readings_prompt(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
