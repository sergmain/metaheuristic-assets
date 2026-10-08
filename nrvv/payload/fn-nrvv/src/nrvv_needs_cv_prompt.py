# mh.asset.nrvv-needs-cv-prompt_1.0 - the CC prompt that judges a project's agreed NEEDs as a set and across their
# trace (plan 045, Phase 9). CC answers through call-cc's result tool; mh.asset.nrvv-needs-cv-check_1.0 checks it.
#
# Inputs  (process metas variable-for-<role>):
#   trace    the agreed NEEDs at the run's snapshot with the requirements each traces to (mhdg-nrvv.read-trace)
# Output:
#   prompt   the prompt for mh.asset.call-cc_1.1
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_needs_cv as cv

FUNCTION_CODE = 'mh.asset.nrvv-needs-cv-prompt_1.0'


def run(task):
    trace = cv.trace_of(io.read_role(task, 'trace'))
    prompt = cv.compose(trace)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(FUNCTION_CODE + ': ' + str(len(trace)) + ' agreed NEED(s), '
          + str(sum(len(n['requirements']) for n in trace)) + ' traced requirement(s), ' + str(len(prompt)) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
