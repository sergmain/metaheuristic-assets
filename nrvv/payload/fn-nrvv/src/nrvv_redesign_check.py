# mh.asset.nrvv-redesign-check_1.0 - check CC's design answer of a re-definition and hand it on in canonical form
# (plan 045, Phase 18).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result         CC's answer, stored through call-cc's result tool: {"items": [...], "add": [...]}
#   definition        the definition context (mhdg-nrvv.read-definition)
#   top-level-answer  the checked top-level answer (mh.asset.nrvv-redefine-check_1.0)
# Output:
#   design-answer     {"items": [...], "add": [...]} - what mhdg-nrvv.store-redefinition reads
#
# Refuses (the Task fails, so finish-run ends the run ERROR and the STAGE is FAILED): not JSON (one markdown fence is
# unwrapped, nothing else), an item outside the items under a CHANGED top-level requirement or named twice, one of them
# left unnamed, an unknown action, an add whose key does not start with D, I or E or whose parent is neither a CHANGED
# top-level requirement nor an added one, a definition left without an Interface or an Environment item, a missing text,
# a guillemet. The Dispatcher checks the same again.
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_redefinition as rd

FUNCTION_CODE = 'mh.asset.nrvv-redesign-check_1.0'


def run(task):
    context = rd.context_of(io.read_role(task, 'definition'))
    top = rd.top_level_of(io.read_role(task, 'top-level-answer'))
    answer = rd.check_design(io.read_role(task, 'cc-result'), context, top)
    io.write_text(io.output_role(task, 'design-answer'), rd.to_json(answer))
    print(FUNCTION_CODE + ': ' + ', '.join(d['action'] + '/' + d['reqId'] for d in answer['items'])
          + (', ADD ' + ', '.join(a['key'] + '<' + a['parent'] for a in answer['add']) if answer['add'] else ''))


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
