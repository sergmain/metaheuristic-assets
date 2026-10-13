# mh.asset.nrvv-expectation-prompt_1.0 - the CC prompt that splits a stakeholder's expectation into clauses, each a
# proposed NEED (plan 047, Phase 6). CC answers through call-cc's result tool; mh.asset.nrvv-expectation-check_1.0
# checks it.
#
# Inputs  (process metas variable-for-<role>):
#   expectation   the expectation, its stakeholder and - for a new version - the agreed NEEDs (mhdg-nrvv.read-expectation)
# Output:
#   prompt        the prompt for mh.asset.call-cc_1.2
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_expectation as ex

FUNCTION_CODE = 'mh.asset.nrvv-expectation-prompt_1.0'


def run(task):
    expectation = ex.expectation_of(io.read_role(task, 'expectation'))
    prompt = ex.compose(expectation)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(FUNCTION_CODE + ': expectation E-' + str(expectation.get('expectationId')) + ', '
          + str(len(ex.pieces(expectation['text']))) + ' piece(s), ' + str(len(expectation['agreedNeeds']))
          + ' agreed NEED(s), ' + str(len(prompt)) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
