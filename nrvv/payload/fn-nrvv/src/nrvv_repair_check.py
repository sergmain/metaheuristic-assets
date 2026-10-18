# mh.asset.nrvv-repair-check_1.0 - check CC's REPAIR answer for one component and hand it on in canonical form.
#
# Inputs  (process metas variable-for-<role>):
#   cc-result         CC's answer, stored through call-cc's result tool: {"decisions": [...], "add": [...]}
#   repair-context    the context the prompt was built from (mhdg-nrvv.read-repair-context)
#   components        this chunk's component, one id
# Output:
#   repair            the checked answer - what mhdg-nrvv.store-repair writes into the STAGE - or {"refused": "<rule>"} when
#                     the answer breaks a rule: the Task still succeeds and the store records one ANSWER_REFUSED
#
# Rules: every item of the component decided exactly once and nothing else named; the answer changes something; the
# evidence rules on every CHANGE and ADD of a top-level requirement or interpretation item; a READING or OPEN_CHOICE
# governs something, an ASSUMPTION nothing; an OBSOLETE leaves every NEED it covered covered; a design, Interface or
# Environment addition names a top-level parent of the component; in an AFTER_INTERPRETATION loop interpretation items
# only. A chunk that is not exactly one component of the context fails the Task - a defect of the flow. The Dispatcher
# checks the same again.

import sys

import mh_task_io as io
import nrvv_repair as wf

FUNCTION_CODE = 'mh.asset.nrvv-repair-check_1.0'


def main(argv):
    wf.run_check(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
