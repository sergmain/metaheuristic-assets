# mh.asset.nrvv-allocation-check_1.0 - check CC's allocation proposals and hand them on in canonical form (plan 045,
# Phase 25).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result            CC's answer, stored through call-cc's result tool: {"findings": [...]}
#   allocation-context   the allocation context the prompt was built from (mhdg-nrvv.read-allocation-input)
# Output:
#   findings             {"findings": [{"kind", "subject", "element" | "shares", "text"}]}, one per requirement to
#                        allocate, in context order - what mhdg-nrvv.store-findings stores
#
# Refuses (the Task fails, so finish-run ends the run ERROR and nothing is stored): not JSON (one markdown fence is
# unwrapped, nothing else), not {"findings": [...]}, an unknown kind or field, a blank text, a subject that is not a
# requirement to allocate or is named twice, a requirement left without a proposal, both or neither of element and
# shares, an unknown element, a split into fewer than two shares, two shares for one element, a blank or too long share
# text. The Dispatcher checks the same again.
#
# Pure but for run()/main().

import json
import sys

import mh_task_io as io
import nrvv_allocation_proposal as ap

FUNCTION_CODE = 'mh.asset.nrvv-allocation-check_1.0'


def run(task):
    context = ap.context_of(io.read_role(task, 'allocation-context'))
    answer = ap.findings_of(io.read_role(task, 'cc-result'), context)
    io.write_text(io.output_role(task, 'findings'), json.dumps(answer, ensure_ascii=False))
    print(FUNCTION_CODE + ': ' + str(len(answer['findings'])) + ' proposal(s): '
          + ', '.join(f['subject'] + '->' + (f['element'] if 'element' in f
                                             else 'split' + str([s['element'] for s in f['shares']]))
                      for f in answer['findings']))


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
