# mh.asset.nrvv-decompose-check_1.0 - check CC's decomposition answer and hand it on, checked, to the design prompt and
# to mhdg-nrvv.store-definition (plan 043, Phase 8). The rules are nrvv_definition.check_decomposition's - the ones
# the store re-checks in the Dispatcher; a broken rule fails this Task before anything reaches RG.
#
# Inputs  (process metas variable-for-<role>):
#   cc-result      CC's answer, stored through call-cc's result tool: {"requirements": [...]}
#   needs          the NEEDs of the run (mhdg-nrvv.read-needs)
# Output:
#   decomposition  the checked answer, single-line JSON, every field stripped
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_definition as nd

FUNCTION_CODE = 'mh.asset.nrvv-decompose-check_1.0'


def run(task):
    checked = nd.check_decomposition(io.read_role(task, 'cc-result'), nd.parse_needs(io.read_role(task, 'needs')))
    io.write_text(io.output_role(task, 'decomposition'), nd.to_json(checked))
    print(FUNCTION_CODE + ': ' + str(len(checked['requirements'])) + ' obligation(s): '
          + ', '.join(r['key'] + ' <- ' + '/'.join(r['needs']) for r in checked['requirements']))


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
