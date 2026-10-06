# mh.asset.nrvv-decompose-prompt_1.0 - the CC prompt that restates a DEFINITION run's NEEDs as obligations (plan 043,
# Phase 8). See nrvv_definition.py.
#
# Inputs  (process metas variable-for-<role>):
#   needs    the NEEDs of the run, as mhdg-nrvv.read-needs wrote them: [{"code", "revision", "title", "statement"}]
# Output:
#   prompt   the prompt for mh.asset.call-cc_1.1
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_definition as nd

FUNCTION_CODE = 'mh.asset.nrvv-decompose-prompt_1.0'


def run(task):
    prompt = nd.compose_decompose_prompt(nd.parse_needs(io.read_role(task, 'needs')))
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(FUNCTION_CODE + ': ' + str(len(prompt)) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
