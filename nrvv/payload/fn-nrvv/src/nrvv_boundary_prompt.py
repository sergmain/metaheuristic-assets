# mh.asset.nrvv-boundary-prompt_1.0 - the prompt of the BOUNDARY session of a definition - the Interface and the Environment.
#
# Roles (process metas variable-for-<role>): boundary-input -> prompt

import sys

import mh_task_io as io
import nrvv_definition_interpreted as wf

FUNCTION_CODE = 'mh.asset.nrvv-boundary-prompt_1.0'


def main(argv):
    wf.run_boundary_prompt(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
