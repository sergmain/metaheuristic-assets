# mh.asset.nrvv-cv-need-expectation-check_1.0 - check CC's EXPECTATION verdicts for one chunk and hand them on in
# canonical form (plan 048, Phase 5).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result      CC's answer, stored through call-cc's result tool: {"verdicts": [...]}
#   agreed-needs   the agreed NEEDs the prompt was built from (mhdg-nrvv.read-agreed-needs)
#   subjects       this chunk's NEEDs, one reqId per line
# Output:
#   findings       {"verdicts": [{"subject", "verdict", "text"}]}, one per NEED of the chunk, in chunk order - what
#                  mhdg-nrvv.store-findings turns into findings (none for FAITHFUL)
#
# Refuses (the Task fails, so finish-run ends the run ERROR and this chunk stores nothing): not JSON (one markdown fence
# is unwrapped, nothing else), not {"verdicts": [...]}, an unknown field or verdict, a blank text on a verdict other than
# FAITHFUL, a text that is not a string, a subject outside the chunk or named twice, a NEED of the chunk left without a
# verdict. The Dispatcher checks the same again.

import sys

import mh_task_io as io
import nrvv_cv_need_expectation as wf

FUNCTION_CODE = 'mh.asset.nrvv-cv-need-expectation-check_1.0'


def main(argv):
    wf.run_check(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
