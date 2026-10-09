# mh.asset.nrvv-trace-prompt_1.0 - the CC prompt that proposes, per orphan of one chunk, how the requirement is
# justified (plan 045, Phase 17). CC answers through call-cc's result tool; mh.asset.nrvv-trace-check_1.0 checks it.
#
# Inputs  (process metas variable-for-<role>):
#   trace-context   the NEEDs, imposed held requirements and orphans at the run's snapshot (mhdg-nrvv.read-drift)
#   orphans         this chunk's orphans, one reqId per line (mh.batch-line-splitter over read-drift's `orphans`)
# Output:
#   prompt          the prompt for mh.asset.call-cc_1.1
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_trace_proposal as tp

FUNCTION_CODE = 'mh.asset.nrvv-trace-prompt_1.0'


def run(task):
    context = tp.context_of(io.read_role(task, 'trace-context'))
    chunk = tp.chunk_of(io.read_role(task, 'orphans'), context)
    prompt = tp.compose(context, chunk)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(FUNCTION_CODE + ': ' + str(len(chunk)) + ' orphan(s) of ' + str(len(context['orphans'])) + ', '
          + str(len(context['needs'])) + ' NEED(s), ' + str(len(context['heldMembers'])) + ' held requirement(s), '
          + str(len(prompt)) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
