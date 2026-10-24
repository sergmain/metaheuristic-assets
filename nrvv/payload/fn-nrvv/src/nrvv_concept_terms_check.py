# mh.asset.nrvv-concept-terms-check_1.0 - check the terms session's answer and give the readings their letters (plan 050 decision 10).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result      the terms session's answer {"terms": [...]}
#   concept-input  what the prompt was built from
# Outputs:
#   terms          {"terms": [{"term", "readings": [{"id", "reading", "quote"}]}], "dropped": [...]}
#   sessions       one readings-session number per line (1 .. CV_REPEAT), for mh.batch-line-splitter
#
# Refuses a wrong shape; a term or reading failing the verbatim rule is dropped and recorded.

import sys

import mh_task_io as io
import nrvv_concept as wf

FUNCTION_CODE = 'mh.asset.nrvv-concept-terms-check_1.0'


def main(argv):
    wf.run_terms_check(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
