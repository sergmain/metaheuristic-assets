# mh.asset.nrvv-define-top-check_1.0 - check one TOP-LEVEL session's requirements; a broken rule is written as a refusal, never a failure.
#
# Roles (process metas variable-for-<role>): cc-result, definition-input, subject -> answer

import sys

import mh_task_io as io
import nrvv_definition_interpreted as wf

FUNCTION_CODE = 'mh.asset.nrvv-define-top-check_1.0'


def main(argv):
    wf.run_top_check(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
