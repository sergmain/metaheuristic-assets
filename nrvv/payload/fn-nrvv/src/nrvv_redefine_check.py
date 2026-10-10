# mh.asset.nrvv-redefine-check_1.0 - check CC's answer for the top-level requirements of a re-definition and hand it on
# in canonical form (plan 045, Phase 18).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result         CC's answer, stored through call-cc's result tool: {"topLevel": [...], "add": [...]}
#   definition        the definition context the prompt was built from (mhdg-nrvv.read-definition)
# Output:
#   top-level-answer  {"topLevel": [...], "add": [...]} - what the design prompt and mhdg-nrvv.store-redefinition read
#
# Refuses (the Task fails, so finish-run ends the run ERROR and the STAGE is FAILED): not JSON (one markdown fence is
# unwrapped, nothing else), an unnamed or twice-named top-level requirement, an unknown action, a citation of a NEED absent
# from the snapshot or not at its current revision, a delta NEED left uncited, a missing text, a guillemet. The Dispatcher
# checks the same again.
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_redefinition as rd

FUNCTION_CODE = 'mh.asset.nrvv-redefine-check_1.0'


def run(task):
    context = rd.context_of(io.read_role(task, 'definition'))
    answer = rd.check_top_level(io.read_role(task, 'cc-result'), context)
    io.write_text(io.output_role(task, 'top-level-answer'), rd.to_json(answer))
    print(FUNCTION_CODE + ': ' + ', '.join(d['action'] + '/' + d['reqId'] for d in answer['topLevel'])
          + (', ADD ' + ', '.join(a['key'] for a in answer['add']) if answer['add'] else ''))


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
