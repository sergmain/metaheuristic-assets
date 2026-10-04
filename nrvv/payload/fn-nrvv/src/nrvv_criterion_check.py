# mh.asset.nrvv-criterion-check_1.0 - check CC's criterion answer inside the requirement's branch and hand on the
# criterion as one line of text (plan 042, Phase 10).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result   CC's answer, stored through call-cc's result tool: {"criterion": "<text>"}
# Output:
#   criterion   the criterion, whitespace collapsed to single spaces - what mhdg-nrvv.store-test-case stores as the
#               TEST_CASE's description
#
# WHY IN THE BRANCH: a bad answer fails ITS branch, visible at that requirement and repaired by resetting that
# branch's cc Task - before anything reaches RG. The byte limit is the TEST_CASE description column's
# (RG_REVISION.DESCRIPTION, VARCHAR(2000); NrvvStoreTestCaseFunction.MAX_CRITERION_BYTES), counted in UTF-8 bytes,
# the stricter measure; store-test-case refuses the same, so an answer that passes here is one it accepts.
#
# Pure but for run()/main().

import json
import re
import sys

import mh_task_io as io

FUNCTION_CODE = 'mh.asset.nrvv-criterion-check_1.0'

MAX_CRITERION_BYTES = 2000

# A model sometimes wraps JSON in a markdown fence. That, and only that, is unwrapped (as mh_rg_req_store does).
FENCE = re.compile(r'^```[A-Za-z]*\s*\n(.*)\n```$', re.DOTALL)
EXCERPT = 300


def excerpt(text):
    text = text or ''
    return text if len(text) <= EXCERPT else text[:EXCERPT] + '...'


def criterion_of(cc_result):
    """The criterion CC answered, as one line - or a ValueError naming what is wrong with the answer."""
    text = (cc_result or '').strip()
    fenced = FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError('CC answered something that is not JSON: ' + excerpt(text)) from None
    if not isinstance(data, dict):
        raise ValueError('CC answered no JSON object {"criterion": ...}: ' + excerpt(text))
    value = data.get('criterion')
    if not isinstance(value, str) or not value.strip():
        raise ValueError('CC answered no criterion: ' + excerpt(text))
    criterion = ' '.join(value.split())
    size = len(criterion.encode('utf-8'))
    if size > MAX_CRITERION_BYTES:
        raise ValueError('the criterion is ' + str(size) + ' UTF-8 bytes, a TEST_CASE description holds at most '
                         + str(MAX_CRITERION_BYTES) + ': ' + excerpt(criterion))
    return criterion


def run(task):
    criterion = criterion_of(io.read_role(task, 'cc-result'))
    io.write_text(io.output_role(task, 'criterion'), criterion)
    print(FUNCTION_CODE + ': ' + excerpt(criterion))


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
