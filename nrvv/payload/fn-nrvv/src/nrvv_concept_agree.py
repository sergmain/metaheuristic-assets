# mh.asset.nrvv-concept-agree_1.0 - the deterministic agreement of the readings sessions and the probe's meta-storage records (plan 050 Phase 2).
#
# Inputs  (process metas variable-for-<role>):
#   terms          the canonical terms
#   all-readings   every session's readings, one JSON object per line (mh.aggregate, type text)
#   label          what the probe ran on (nullable)
#   production     nullable; only 'true' selects the production meta store
# Outputs:
#   records        the meta-storage records {type, recKey, body}: one per term, then summary
#   summary        the agreement and its counts
#   meta-storage-type, synthetic-flag, table-desc, table-rec-key-format, table-body-format, table-consumer
#                  for mh.meta-storage-registry and mh.meta-storage

import sys

import mh_task_io as io
import nrvv_concept as wf

FUNCTION_CODE = 'mh.asset.nrvv-concept-agree_1.0'


def main(argv):
    wf.run_agree(io.load_params(argv)['task'], FUNCTION_CODE)


if __name__ == '__main__':
    main(sys.argv)
