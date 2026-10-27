# mh.asset.nrvv-criterion-prompt_1.0 - the CC prompt that derives ONE pass/fail verification criterion for one
# requirement (plan 042, Phase 10; savepoint lookup 4, decision B): the criterion becomes the TEST_CASE's text in RG,
# and the tests are written against it.
#
# Inputs  (process metas variable-for-<role>):
#   req-id       the requirement's current reqId - the splitter's line
#   requirement  the requirement as mhdg-rg.read-req read it at the run's STAGE (RG document markup)
#   constraints  optional (plan 047 Phase 20, decision 15): every ACTIVE requirement of the scope's snapshot as
#                "<reqId>: <requirement content>" blocks (mhdg-nrvv.list-scope's scopeRequirements) - read-only; a flow
#                without the meta passes none
# Output:
#   prompt       the prompt for mh.asset.call-cc_1.1
#
# FROM THE REQUIREMENT ALONE: the prompt carries the requirement's text - all four items, so a filled Acceptance item
# is used whenever recovery provided one - and never target code (decision 17). CC answers through call-cc's result
# tool with ONE JSON object; mh.asset.nrvv-criterion-check_1.0 checks it. Since plan 050 Phase 17: with the criterion
# itself, plain text - no JSON.
#
# LANGUAGE-NEUTRAL (correction C3): the requirement was recovered from code in one language and is implemented in
# another, so a requirement about a construct of the source language (a declaration, an access modifier, a return
# type, compiling, a printing call) is stated as the observable behaviour it implies - TA2 and TA4 criteria named
# 'public', 'void', 'NrvvSample.java' and System.out.println, which a Python implementation cannot meet literally.
#
# Pure but for run()/main().

import sys

import mh_task_io as io
import nrvv_requirement_text as rt

FUNCTION_CODE = 'mh.asset.nrvv-criterion-prompt_1.0'

# the criterion check refuses more than 2000 UTF-8 bytes (the TEST_CASE description column); asking for far less
# leaves room for a model that overshoots
ASKED_MAX_CHARS = 600


def constraints_section(constraints):
    """Plan 047 Phase 20 (decision 15): the scope's requirements as read-only constraints; none when there are none."""
    text = (constraints or '').strip()
    if not text:
        return []
    return [
        'The requirements in force in this scope - read-only constraints. No criterion may expect behaviour one of',
        'them forbids; they are context, not requirements to derive a criterion for:',
        '',
        text,
        '',
    ]


def compose(req_id, content, constraints=None):
    """The prompt for requirement req_id, or a ValueError when there is nothing to derive a criterion from."""
    req = (req_id or '').strip()
    if not req:
        raise ValueError('req-id is empty')
    text = rt.plain_text(content)
    if not text:
        raise ValueError('requirement ' + req + ' has no text')
    # plan 047 Phase 20 (by its characterization test): the "recovered from code in one language" framing is said only
    # of a requirement recovered from code - one with a "source:" line; a defined requirement is language-neutral already
    recovered = rt.source_citation(content) is not None
    recovery_rules = [
        '- The requirement was recovered from code in one language and will be implemented in another. Word the',
        '  criterion so it holds in ANY implementation language: when the requirement is about a construct of the',
        '  source language - a class or method declaration, an access modifier, a parameter list or a return type,',
        '  compiling, a particular printing call - state the observable behaviour it implies (a named unit exists',
        '  and can be called; calling it produces the stated output or result), never the construct itself.',
        '- The Rationale\'s "source:" line says where the requirement was recovered from; it is not part of the',
        '  criterion.',
    ] if recovered else []
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
    ] + recovery_rules + [
        '',
        # plan 045 Phase 36 (2026-10-10, by CT): the answer instruction moved to the END - after reading the requirement
        # last, haiku reasoned about it and printed {"criterion": ...} instead of calling the result tool (acceptance
        # runs CRITERIA #96, #99), and call-cc failed the Task. It was:
        #   'Store your answer with the result tool as exactly this JSON object, and nothing else:',
        #   '{"criterion": "<the criterion>"}',
        #   '',
    ] + constraints_section(constraints) + [
        'Requirement ' + req + ':',
        text,
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with the criterion itself as the result: plain text'
        ' - not JSON, not quoted, no markdown fence, nothing before or after it.',
        # plan 050 Phase 17 (by its characterization test test_the_criterion_prompt_asks_for_the_criterion_itself): the
        # criterion itself - (b) #120's escaped closing quote ended CRITERIA #3598 ERROR. The two lines above were:
        #   'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object, and nothing else:',
        #   '{"criterion": "<the criterion>"}',
        'Print nothing - neither the criterion nor any explanation: only what the tool stores reaches the pipeline.',
    ])


def run(task):
    # plan 047 Phase 20: the constraints role is optional - nrvv-criteria-1.0 does not pass it, nrvv-criteria-1.2 does
    constraints = io.read_role(task, 'constraints') if io.meta_value(task.get('metas') or [], 'variable-for-constraints') else None
    prompt = compose(io.read_role(task, 'req-id'), io.read_role(task, 'requirement'), constraints)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(FUNCTION_CODE + ': ' + str(len(prompt)) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
