# mh.asset.nrvv-criterion-prompt_1.0 - the CC prompt that derives ONE pass/fail verification criterion for one
# requirement (plan 042, Phase 10; savepoint lookup 4, decision B): the criterion becomes the TEST_CASE's text in RG,
# and the tests are written against it.
#
# Inputs  (process metas variable-for-<role>):
#   req-id       the requirement's current reqId - the splitter's line
#   requirement  the requirement as mhdg-rg.read-req read it at the run's STAGE (RG document markup)
# Output:
#   prompt       the prompt for mh.asset.call-cc_1.1
#
# FROM THE REQUIREMENT ALONE: the prompt carries the requirement's text - all four items, so a filled Acceptance item
# is used whenever recovery provided one - and never target code (decision 17). CC answers through call-cc's result
# tool with ONE JSON object; mh.asset.nrvv-criterion-check_1.0 checks it.
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_requirement_text as rt

FUNCTION_CODE = 'mh.asset.nrvv-criterion-prompt_1.0'

# the criterion check refuses more than 2000 UTF-8 bytes (the TEST_CASE description column); asking for far less
# leaves room for a model that overshoots
ASKED_MAX_CHARS = 600


def compose(req_id, content):
    """The prompt for requirement req_id, or a ValueError when there is nothing to derive a criterion from."""
    req = (req_id or '').strip()
    if not req:
        raise ValueError('req-id is empty')
    text = rt.plain_text(content)
    if not text:
        raise ValueError('requirement ' + req + ' has no text')
    return '\n'.join([
        'You derive the verification criterion of ONE requirement of a software system.',
        '',
        'A verification criterion is ONE pass/fail condition on observable behaviour: what a test does and what it',
        'must observe for the requirement to count as met. Derive it from the requirement below and from nothing',
        'else - you have no code, and you must not assume any.',
        '',
        'Rules:',
        '- Exactly one criterion, plain text, one paragraph, at most ' + str(ASKED_MAX_CHARS) + ' characters.',
        '- Observable: the action or input, and the exact expected output, return value or state. Quote every exact',
        '  literal the requirement names.',
        '- When the Acceptance item states a condition (anything but "Not applicable"), base the criterion on it.',
        '- Name no test framework, no file and no programming language.',
        '- The Rationale\'s "source:" line says where the requirement was recovered from; it is not part of the',
        '  criterion.',
        '',
        'Store your answer with the result tool as exactly this JSON object, and nothing else:',
        '{"criterion": "<the criterion>"}',
        '',
        'Requirement ' + req + ':',
        text,
    ])


def run(task):
    prompt = compose(io.read_role(task, 'req-id'), io.read_role(task, 'requirement'))
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(FUNCTION_CODE + ': ' + str(len(prompt)) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
