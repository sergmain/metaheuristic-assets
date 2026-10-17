# mh.asset.nrvv-interpretation-check_1.0 - check CC's items for one session of a NEED interpretation and hand them on
# in canonical form.
#
# Inputs  (process metas variable-for-<role>):
#   cc-result             CC's answer, stored through call-cc's result tool: {"items": [...]}
#   interpretation-input  the input the prompt was built from (mhdg-nrvv.read-interpretation-input)
#   session               the session's id
# Output:
#   interpretation        {"items": [...]} in canonical form, or {"refused": "<rule>"} when the answer breaks a rule -
#                         the Task still succeeds: the store records the refusal and writes nothing for the session
#
# Rules: the kinds; keys unique with the session's prefix; needs within the session; governs within the session's
# governable (* in the global session only), required on READING and OPEN_CHOICE, absent on ASSUMPTION; every
# qualifier NEED of the session cited; the evidence rules (nrvv_evidence: quote, universal word, language). The
# Dispatcher checks the same again.

import sys

import mh_task_io as io
import nrvv_interpretation as wf

FUNCTION_CODE = 'mh.asset.nrvv-interpretation-check_1.0'


def main(argv):
    wf.run_check(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
