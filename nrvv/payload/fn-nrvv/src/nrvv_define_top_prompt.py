# mh.asset.nrvv-define-top-prompt_1.0 - the prompt of one TOP-LEVEL session of a definition under the interpretation (one derivation NEED).
#
# Roles (process metas variable-for-<role>): definition-input, subject -> prompt

import sys

import mh_task_io as io
import nrvv_definition_interpreted as wf

FUNCTION_CODE = 'mh.asset.nrvv-define-top-prompt_1.0'


def main(argv):
    wf.run_top_prompt(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
