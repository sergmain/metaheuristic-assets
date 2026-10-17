# mh.asset.nrvv-interpretation-prompt_1.0 - the prompt of one session of a NEED interpretation. CC answers through
# call-cc's result tool; mh.asset.nrvv-interpretation-check_1.0 checks it.
#
# Inputs  (process metas variable-for-<role>):
#   interpretation-input  the NEEDs, sections and sessions (mhdg-nrvv.read-interpretation-input)
#   session               the session's id - firstSession, or one line of localSessions
#   first-answer          optional: the first session's checked answer, shown read-only to a later session
# Output:
#   prompt                the prompt for mh.asset.call-cc_1.2

import sys

import mh_task_io as io
import nrvv_interpretation as wf

FUNCTION_CODE = 'mh.asset.nrvv-interpretation-prompt_1.0'


def main(argv):
    wf.run_prompt(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
