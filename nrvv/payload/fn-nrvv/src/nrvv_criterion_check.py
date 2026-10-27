# mh.asset.nrvv-criterion-check_1.0 - check CC's criterion answer inside the requirement's branch and hand on the
# criterion as one line of text (plan 042, Phase 10).
#
# Inputs  (process metas variable-for-<role>):
#   cc-result   CC's answer, stored through call-cc's result tool: {"criterion": "<text>"}
#               - since plan 050 Phase 17: the criterion itself, plain text (see below)
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
#
# Since plan 050 Phase 17 (2026-10-26, by its characterization test test_the_criterion_answer_is_the_criterion_itself):
# the answer IS the criterion - no JSON object around it. Acceptance run (b) #120 on CC: one answer (Variable 218630) closed
# its criterion with an escaped quote, the JSON string never ended, this check raised and CRITERIA #3598 ended ERROR -
# the nested-escaping slip of TEST_AUTHOR's answers (deviation 17), here in prose. An answer still in the former form is
# refused by name: taken as text it would be stored as the criterion.

import json
import re
import sys

import mh_task_io as io

FUNCTION_CODE = 'mh.asset.nrvv-criterion-check_1.0'

MAX_CRITERION_BYTES = 2000

# A model sometimes wraps its answer in a markdown fence. That, and only that, is unwrapped (as mh_rg_req_store does).
FENCE = re.compile(r'^```[A-Za-z]*\s*\n(.*)\n```$', re.DOTALL)
EXCERPT = 300


def excerpt(text):
    text = text or ''
    return text if len(text) <= EXCERPT else text[:EXCERPT] + '...'


def criterion_of(cc_result):
    """The criterion CC answered, as one line - or a ValueError naming what is wrong with the answer. The answer is the
    criterion itself (plan 050 Phase 17)."""
    text = (cc_result or '').strip()
    fenced = FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    # a JSON-shaped answer - the former {"criterion": ...} or any other object or list - is no criterion; taken as text it
    # would be stored as one
    if text[:1] in ('{', '['):
        raise ValueError('CC answered the former JSON form {"criterion": ...} - the criterion itself is asked for: '
                         + excerpt(text))
    if not text:
        raise ValueError('CC answered no criterion')
    criterion = ' '.join(text.split())
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
