# mh.asset.nrvv-cv-need-completeness-check_1.0 - check CC's COMPLETENESS verdicts for one chunk of NEEDs and hand them
# on in canonical form.
#
# Inputs  (process metas variable-for-<role>):
#   cc-result             CC's answer, stored through call-cc's result tool: {"verdicts": [...]}
#   completeness-context  the context the prompt was built from (mhdg-nrvv.read-completeness-input)
#   subjects              this chunk's NEEDs, one reqId per line
# Output:
#   findings              {"verdicts": [{"subject", "verdict", "text"?}]}, one per NEED of the chunk, in chunk order -
#                         what mhdg-nrvv.store-findings turns into findings (NEED_NOT_MET per NOT_MET) - or
#                         {"refused": "<rule>", "subjects": [<the chunk>]} when the answer breaks a rule: the Task still
#                         succeeds and the store records the refusal per NEED of the chunk
#
# Rules: not JSON (one markdown fence is unwrapped, nothing else), not {"verdicts": [...]}, an unknown field or verdict,
# a subject outside the chunk or named twice, a NEED of the chunk left without a verdict, NOT_MET without its situation.
# A chunk naming a NEED the context does not hold fails the Task - a defect of the flow. The Dispatcher checks the same
# again.

import sys

import mh_task_io as io
import nrvv_cv_need_completeness as wf

FUNCTION_CODE = 'mh.asset.nrvv-cv-need-completeness-check_1.0'


def main(argv):
    wf.run_check(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
