# mh.asset.nrvv-redesign-prompt_1.0 - the CC prompt that carries the changed and added top-level requirements of a
# re-definition into its design, Interface and Environment items (plan 045, Phase 18). CC answers through call-cc's
# result tool; mh.asset.nrvv-redesign-check_1.0 checks it.
#
# Inputs  (process metas variable-for-<role>):
#   definition        the definition context at the run's snapshot (mhdg-nrvv.read-definition)
#   top-level-answer  the checked top-level answer (mh.asset.nrvv-redefine-check_1.0)
# Output:
#   prompt            the prompt for mh.asset.call-cc_1.1
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_redefinition as rd

FUNCTION_CODE = 'mh.asset.nrvv-redesign-prompt_1.0'


def run(task):
    context = rd.context_of(io.read_role(task, 'definition'))
    top = rd.top_level_of(io.read_role(task, 'top-level-answer'))
    prompt = rd.compose_design(context, top)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(FUNCTION_CODE + ': ' + str(len(rd.items_to_answer(context, top))) + ' item(s) to answer, '
          + str(len(prompt)) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
