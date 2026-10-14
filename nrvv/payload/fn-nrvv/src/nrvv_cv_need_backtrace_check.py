# mh.asset.nrvv-cv-need-backtrace-check_1.0 - check CC's BACKTRACE verdicts for one chunk and hand them on in canonical
# form (plan 047, Phase 17).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result           CC's answer, stored through call-cc's result tool: {"verdicts": [...]}
#   backtrace-context   the context the prompt was built from (mhdg-nrvv.read-backtrace-input)
#   subjects            this chunk's subjects, one reqId per line
# Output:
#   findings            {"verdicts": [{"subject", "verdict", "needReqIds"?, "needReqId"?, "text"}]}, one per subject of the
#                       chunk, in chunk order - what mhdg-nrvv.store-findings turns into findings (none for JUSTIFIED)
#
# Refuses (the Task fails, so finish-run ends the run ERROR and this chunk stores nothing): not JSON (one markdown fence
# is unwrapped, nothing else), not {"verdicts": [...]}, an unknown field or verdict, a blank text, a subject outside the
# chunk or named twice, a subject of the chunk left without a verdict, JUSTIFIED without an agreed NEED, CONTRADICTS_NEED
# without an agreed NEED, RESTS_ON_SUPERSEDED without a NEED the subject cites at a revision no longer in force, UNNEEDED
# on an owned requirement, OVER_REACH on a held one, a field the verdict does not use. The Dispatcher checks the same again.

import sys

import mh_task_io as io
import nrvv_cv_need_backtrace as wf

FUNCTION_CODE = 'mh.asset.nrvv-cv-need-backtrace-check_1.0'


def main(argv):
    wf.run_check(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
