# mh.asset.nrvv-design-check_1.0 - check CC's design answer against the checked obligations and hand it on, checked,
# to mhdg-nrvv.store-definition (plan 043, Phase 8). The rules are nrvv_definition.check_design's - the ones the store
# re-checks in the Dispatcher; a broken rule fails this Task before anything reaches RG.
#
# Inputs  (process metas variable-for-<role>):
#   cc-result      CC's answer, stored through call-cc's result tool: {"design", "interface", "environment"}
#   decomposition  the checked obligations (mh.asset.nrvv-decompose-check_1.0)
# Output:
#   design         the checked answer, single-line JSON, every field stripped
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_definition as nd

FUNCTION_CODE = 'mh.asset.nrvv-design-check_1.0'


def run(task):
    checked = nd.check_design(io.read_role(task, 'cc-result'), nd.parse_decomposition(io.read_role(task, 'decomposition')))
    io.write_text(io.output_role(task, 'design'), nd.to_json(checked))
    print(FUNCTION_CODE + ': ' + ', '.join(name + ' ' + str(len(checked[name])) for name in ('design', 'interface', 'environment')))


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
