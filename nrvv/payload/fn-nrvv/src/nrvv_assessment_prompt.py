# mh.asset.nrvv-assessment-prompt_1.0 - the CC prompt that assesses ONE proposed NEED against the project's agreed
# NEEDs (plan 045, Phase 7). CC answers through call-cc's result tool; mh.asset.nrvv-assessment-check_1.0 checks it.
#
# Inputs  (process metas variable-for-<role>):
#   proposal      the proposal as the Dispatcher froze it into the run (NrvvAssessmentUtils.proposalJson)
#   agreed-needs  the agreed NEEDs at the run's snapshot (mhdg-nrvv.read-agreed-needs; [] when the project has none)
# Output:
#   prompt        the prompt for mh.asset.call-cc_1.1
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_assessment as na

FUNCTION_CODE = 'mh.asset.nrvv-assessment-prompt_1.0'


def run(task):
    proposal = na.proposal_of(io.read_role(task, 'proposal'))
    needs = na.agreed_needs_of(io.read_role(task, 'agreed-needs'))
    prompt = na.compose(proposal, needs)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(FUNCTION_CODE + ': ' + str(proposal.get('ref')) + ' against ' + str(len(needs)) + ' agreed NEED(s), '
          + str(len(prompt)) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
