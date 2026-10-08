# mh.asset.nrvv-wording-prompt_1.0 - the CC prompt that words ONE amendment of an agreed NEED as a person's
# instruction says (plan 045, Phase 8). CC answers through call-cc's result tool; mh.asset.nrvv-wording-check_1.0
# checks it.
#
# Inputs  (process metas variable-for-<role>):
#   proposal          the proposal as the Dispatcher froze it into the run (NrvvAssessmentUtils.proposalJson)
#   wording-request   what to word (NrvvWordingUtils.wordingRequestJson): {"targetNeedReqId", "instruction"}
#   agreed-needs      the agreed NEEDs at the run's snapshot (mhdg-nrvv.read-agreed-needs); the target is one of them
# Output:
#   prompt            the prompt for mh.asset.call-cc_1.1
#
# Refuses (the Task fails): a target that is not one of the agreed NEEDs at the run's snapshot.
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_assessment as na
import nrvv_wording as nw

FUNCTION_CODE = 'mh.asset.nrvv-wording-prompt_1.0'


def run(task):
    proposal = na.proposal_of(io.read_role(task, 'proposal'))
    request = nw.request_of(io.read_role(task, 'wording-request'))
    needs = na.agreed_needs_of(io.read_role(task, 'agreed-needs'))
    prompt = nw.compose(proposal, request, needs)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(FUNCTION_CODE + ': ' + str(proposal.get('ref')) + ' amends ' + str(request.get('targetNeedReqId')) + ', '
          + str(len(needs)) + ' agreed NEED(s), ' + str(len(prompt)) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
