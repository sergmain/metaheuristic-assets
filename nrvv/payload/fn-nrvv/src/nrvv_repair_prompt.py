# mh.asset.nrvv-repair-prompt_1.0 - the REPAIR prompt for one component: its findings, the items they name, the items
# those are read under, the NEEDs with what covers them, the "which side" rules and the loop's earlier iterations. CC
# answers through call-cc's result tool; mh.asset.nrvv-repair-check_1.0 checks it.
#
# Inputs  (process metas variable-for-<role>):
#   repair-context    every component of the REPAIR (mhdg-nrvv.read-repair-context's repairContext)
#   components        this chunk's component, one id (mh.batch-line-splitter over read-repair-context's `components`)
# Output:
#   prompt            the prompt for mh.asset.call-cc_1.2

import sys

import mh_task_io as io
import nrvv_repair as wf

FUNCTION_CODE = 'mh.asset.nrvv-repair-prompt_1.0'


def main(argv):
    wf.run_prompt(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
