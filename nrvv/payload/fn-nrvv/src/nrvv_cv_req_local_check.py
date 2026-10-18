# mh.asset.nrvv-cv-req-local-check_1.0 - check CC's LOCAL_CONTRADICTION answer for one requirement and hand it on in
# canonical form.
#
# Inputs  (process metas variable-for-<role>):
#   cc-result         CC's answer, stored through call-cc's result tool: {"subject", "contradictions": [...]}
#   local-cv-context  the context the prompt was built from (mhdg-nrvv.read-local-cv-input)
#   subjects          this chunk's subject, one reqId
# Output:
#   findings          {"subject", "contradictions": [{"counterpart", "text"}]} - what mhdg-nrvv.store-findings turns into
#                     one REQ_CONTRADICTION per counterpart - or {"refused": "<rule>", "subjects": [<the subject>]} when
#                     the answer breaks a rule: the Task still succeeds and the store records the refusal
#
# Rules: not JSON (one markdown fence is unwrapped, nothing else), not {"subject", "contradictions": [...]}, an answer on
# another requirement, an unknown field, a counterpart that is not a candidate or named twice, a contradiction without
# its situation. A chunk that is not exactly one subject of the context fails the Task - a defect of the flow. The
# Dispatcher checks the same again.

import sys

import mh_task_io as io
import nrvv_cv_req_local as wf

FUNCTION_CODE = 'mh.asset.nrvv-cv-req-local-check_1.0'


def main(argv):
    wf.run_check(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
