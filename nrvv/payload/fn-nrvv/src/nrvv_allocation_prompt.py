# mh.asset.nrvv-allocation-prompt_1.0 - the CC prompt that proposes, per unallocated top-level requirement, the element
# that must meet it or a split into per-element shares (plan 045, Phase 25). CC answers through call-cc's result tool;
# mh.asset.nrvv-allocation-check_1.0 checks it.
#
# Inputs  (process metas variable-for-<role>):
#   allocation-context   the elements, the requirements to allocate, the design and the allocations in force at the run's
#                        snapshot (mhdg-nrvv.read-allocation-input)
# Output:
#   prompt               the prompt for mh.asset.call-cc_1.1
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_allocation_proposal as ap

FUNCTION_CODE = 'mh.asset.nrvv-allocation-prompt_1.0'


def run(task):
    context = ap.context_of(io.read_role(task, 'allocation-context'))
    prompt = ap.compose(context)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(FUNCTION_CODE + ': ' + str(len(context['topLevel'])) + ' requirement(s) to allocate, '
          + str(len(context['elements'])) + ' element(s), ' + str(len(context['items'])) + ' design item(s), '
          + str(len(prompt)) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
