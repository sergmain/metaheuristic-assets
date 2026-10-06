# mh.asset.nrvv-env-prompt_1.0 - the CC prompt for the simulated environment `nrvv_env` of a definition snapshot (plan
# 043, Phase 9). See nrvv_environment.py.
#
# Inputs  (process metas variable-for-<role>):
#   design   the design mhdg-nrvv.list-scope wrote: {"interface": [{"reqId", "content"}], "environment": [...]}
# Output:
#   prompt   the prompt for mh.asset.call-cc_1.1
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_environment as ne

FUNCTION_CODE = 'mh.asset.nrvv-env-prompt_1.0'


def run(task):
    prompt = ne.compose_env_prompt(ne.parse_design(io.read_role(task, 'design')))
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(FUNCTION_CODE + ': ' + str(len(prompt)) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
