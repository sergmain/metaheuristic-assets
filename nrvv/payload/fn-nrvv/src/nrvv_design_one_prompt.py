# mh.asset.nrvv-design-one-prompt_1.0 - the prompt of one DESIGN session of a definition (one top-level requirement).
#
# Roles (process metas variable-for-<role>): design-input, branch -> prompt

import sys

import mh_task_io as io
import nrvv_definition_interpreted as wf

FUNCTION_CODE = 'mh.asset.nrvv-design-one-prompt_1.0'


def main(argv):
    wf.run_design_prompt(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
