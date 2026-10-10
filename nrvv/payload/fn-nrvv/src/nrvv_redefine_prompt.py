# mh.asset.nrvv-redefine-prompt_1.0 - the CC prompt that carries a NEED change into the top-level requirements of a
# definition (plan 045, Phase 18). CC answers through call-cc's result tool; mh.asset.nrvv-redefine-check_1.0 checks it.
#
# Inputs  (process metas variable-for-<role>):
#   definition      the definition context at the run's snapshot (mhdg-nrvv.read-definition)
# Output:
#   prompt          the prompt for mh.asset.call-cc_1.1
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_redefinition as rd

FUNCTION_CODE = 'mh.asset.nrvv-redefine-prompt_1.0'


def run(task):
    context = rd.context_of(io.read_role(task, 'definition'))
    prompt = rd.compose_top_level(context)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(FUNCTION_CODE + ': ' + str(len(context['topLevel'])) + ' top-level requirement(s), ' + str(len(context['needs']))
          + ' NEED(s), delta ' + str(context['delta']) + ', ' + str(len(prompt)) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
