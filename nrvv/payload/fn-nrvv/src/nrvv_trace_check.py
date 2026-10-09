# mh.asset.nrvv-trace-check_1.0 - check CC's trace proposals for one chunk and hand them on in canonical form
# (plan 045, Phase 17).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result       CC's answer, stored through call-cc's result tool: {"findings": [...]}
#   trace-context   the trace context the prompt was built from (mhdg-nrvv.read-drift)
#   orphans         this chunk's orphans, one reqId per line
# Output:
#   findings        {"findings": [{"kind", "subject", "counterpart"?, "text"}]}, one per orphan of the chunk, in chunk
#                   order - what mhdg-nrvv.store-findings stores
#
# Refuses (the Task fails, so finish-run ends the run ERROR and this chunk stores nothing): not JSON (one markdown fence
# is unwrapped, nothing else), not {"findings": [...]}, an unknown kind or field, a blank text, a subject outside the
# chunk or named twice, an orphan of the chunk left without a proposal, a counterpart its kind does not allow, a link
# proposed for an orphan that is not top-level. The Dispatcher checks the same again.
#
# Pure but for run()/main().

import json
import sys

import mh_task_io as io
import nrvv_trace_proposal as tp

FUNCTION_CODE = 'mh.asset.nrvv-trace-check_1.0'


def run(task):
    context = tp.context_of(io.read_role(task, 'trace-context'))
    chunk = tp.chunk_of(io.read_role(task, 'orphans'), context)
    answer = tp.findings_of(io.read_role(task, 'cc-result'), context, chunk)
    io.write_text(io.output_role(task, 'findings'), json.dumps(answer, ensure_ascii=False))
    print(FUNCTION_CODE + ': ' + str(len(answer['findings'])) + ' proposal(s): '
          + ', '.join(f['kind'] + '/' + f['subject'] + ('/' + f['counterpart'] if 'counterpart' in f else '')
                      for f in answer['findings']))


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
