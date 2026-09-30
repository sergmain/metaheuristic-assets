# mh.asset.rg-req-first_1.0 - split every file's collected answer into the ONE requirement that becomes the
# project's genesis and the requirements that go into the STAGE forked from it.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# rg-requirements/functions/fn-rg-req-first/mh-function.yaml.
#
# roles - every Variable is named by a meta, never hard-coded:
#   paths         INPUT  - the batch, one path per line, exactly what mh.batch-line-splitter split
#   answers       INPUT  - every branch's answer as mh.asset.rg-req-check_1.0 wrote it, collected by mh.aggregate
#   first-path    OUTPUT - the file requirement #1 comes from: the batch's first path
#   first-answer  OUTPUT - ONE answer line holding ONLY requirement #1 - what internal mhdg-rg.req-store-batch takes
#                          (with first-path as its batch) to run the project's genesis on that one requirement
#   other-reqs    OUTPUT - every other requirement, one JSON line each, in the batch's order: {name, content,
#                          rationale, type} - what internal mh.batch-line-splitter hands internal mhdg-rg.store-req as reqJson
#   has-first     OUTPUT - 'true' when there is a requirement #1, the flag the storing mh.nop is gated on
#
# EVERY FILE OR NOTHING, before anything is stored: the answers must cover the batch exactly - the same plan() the
# batch store runs - so a file whose branch never answered stops the run here, not after the genesis has fired.
#
# EVERY LINE SAYS type DERIVED. store-req reads an ABSENT type as DECOMPOSED - CC's decomposition output - and these
# are manual requirements, DERIVED like requirement #1 that req-store-batch writes. RG's own manual path states it the
# same way (RgStoreReq.authoredRequirementLine). Without it ExecContext #24 stored #1 DERIVED and the 463 others
# DECOMPOSED.
#
# The other-reqs lines carry only the fields store-req's RequirementLine reads, and no 'source:' line in the
# rationale: store-req composes its four items one line each and numbers them by counting, so an extra line would be
# numbered as the next item. Requirement #1 goes through req-store-batch, which adds its own 'source:' line.

import json
import sys

from mh_rg_req_store_batch import parse_answers, plan
from mh_task_io import load_params, output_role, read_role, write_text

FUNCTION_CODE = 'mh.asset.rg-req-first_1.0'

# RgEnums.RequirementType of a manual requirement - written by a human (here: CC, one file at a time), not decomposed
DERIVED = 'DERIVED'


def store_req_line(requirement):
    """One requirement as one ASCII JSON line with only the fields store-req reads - type DERIVED, stated, never left
    to store-req's default (DECOMPOSED)."""
    item = {}
    name = requirement.get('name')
    if isinstance(name, str) and name.strip():
        item['name'] = name.strip()
    item['content'] = requirement['content']
    rationale = requirement.get('rationale')
    if isinstance(rationale, str) and rationale.strip():
        item['rationale'] = rationale
    item['type'] = DERIVED
    return json.dumps(item, ensure_ascii=True)


def first_and_others(paths_text, answers_text):
    """(first_path, first_answer_line, [other store-req lines]) - or the failure naming what does not cover the
    batch."""
    pairs = plan(paths_text, parse_answers(answers_text))
    first_path, first_requirement = pairs[0]
    first_answer = json.dumps({'sourcePath': first_path, 'requirements': [first_requirement]}, ensure_ascii=True)
    return first_path, first_answer, [store_req_line(requirement) for _, requirement in pairs[1:]]


def main(argv):
    print(FUNCTION_CODE)
    params = load_params(argv)
    task = params['task']
    try:
        first_path, first_answer, others = first_and_others(read_role(task, 'paths'), read_role(task, 'answers'))
        # every output resolved before any is written
        targets = [output_role(task, role) for role in ('first-path', 'first-answer', 'other-reqs', 'has-first')]
        for target, text in zip(targets, (first_path, first_answer, '\n'.join(others), 'true')):
            write_text(target, text)
        print('requirement #1 from ' + first_path + '; ' + str(len(others)) + ' other requirement(s)')
        return 0
    except (ValueError, OSError) as e:
        print('FAILED: ' + str(e))
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
