# mh.asset.nrvv-design-prompt_1.0 - the CC prompt that asks for the design, the Interface and the Environment meeting a
# DEFINITION run's checked obligations (plan 043, Phase 8). See nrvv_definition.py.
#
# Inputs  (process metas variable-for-<role>):
#   needs          the NEEDs of the run (mhdg-nrvv.read-needs)
#   decomposition  the checked obligations (mh.asset.nrvv-decompose-check_1.0)
# Output:
#   prompt         the prompt for mh.asset.call-cc_1.1
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_definition as nd

FUNCTION_CODE = 'mh.asset.nrvv-design-prompt_1.0'


def run(task):
    prompt = nd.compose_design_prompt(nd.parse_needs(io.read_role(task, 'needs')),
                                      nd.parse_decomposition(io.read_role(task, 'decomposition')))
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(FUNCTION_CODE + ': ' + str(len(prompt)) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
