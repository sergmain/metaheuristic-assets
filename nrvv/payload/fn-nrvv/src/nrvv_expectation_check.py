# mh.asset.nrvv-expectation-check_1.0 - check CC's split of an expectation into clauses and hand it on in canonical
# form (plan 047, Phase 6).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result     CC's answer, stored through call-cc's result tool: {"clauses": [...]}
#   expectation   the expectation the prompt listed - spans must lie inside its text; a mapping must name its NEEDs
# Output:
#   clauses       {"clauses": [{"from", "to", "kind", "title", "statement", "mapping"?, "needReqId"?}]}, ordered by
#                 from - what mhdg-nrvv.store-expectation-analysis stores
#
# Refuses (the Task fails, so finish-run ends the run ERROR and nothing is stored): not JSON (one markdown fence is
# unwrapped, nothing else), not {"clauses": [...]}, no clause, an unknown field, a span outside the text, empty or
# overlapping another, a kind outside the clause kinds, an empty title or statement, a mapping on an expectation
# without a parent, AMENDS / UNCHANGED without an agreed NEED's reqId, a NEED named twice, NEW naming a NEED. The
# Dispatcher checks the same again.
#
# Pure but for run()/main().

import json
import sys

import mh_task_io as io
import nrvv_expectation as ex

FUNCTION_CODE = 'mh.asset.nrvv-expectation-check_1.0'


def run(task):
    expectation = ex.expectation_of(io.read_role(task, 'expectation'))
    answer = ex.clauses_of(io.read_role(task, 'cc-result'), expectation)
    io.write_text(io.output_role(task, 'clauses'), json.dumps(answer, ensure_ascii=False))
    print(FUNCTION_CODE + ': ' + str(len(answer['clauses'])) + ' clause(s): '
          + ', '.join('[' + str(c['from']) + ',' + str(c['to']) + ') ' + c['kind']
                      + ('/' + c['mapping'] + ('/' + c['needReqId'] if c.get('needReqId') else '') if 'mapping' in c else '')
                      for c in answer['clauses']))


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
