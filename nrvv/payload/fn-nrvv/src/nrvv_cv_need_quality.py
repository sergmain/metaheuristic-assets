# NEED check QUALITY (plan 047, Phase 10): the wording of each agreed NEED - VAGUE_TERM, SOLUTION_STATEMENT,
# SYSTEM_VOICE, NOT_SINGULAR - and REDUNDANCY between two of them. Every QUALITY finding is soft: it is recorded and
# listed with the run, it never gates (decision 10). Run once per gate (decision 13).
#
# Pure: the prompt and the kinds. The Task runners are nrvv_cv_need_quality_prompt.py / _check.py.

import nrvv_cv_need as cv

KINDS = ('VAGUE_TERM', 'SOLUTION_STATEMENT', 'SYSTEM_VOICE', 'NOT_SINGULAR', 'REDUNDANCY')
PAIR_KINDS = ('REDUNDANCY',)


def compose(needs):
    """The quality prompt over the agreed NEEDs."""
    lines = [
        'You review the wording of the NEEDs a project\'s stakeholders have agreed. You do not decide anything and you',
        'never rewrite a NEED: each finding is recorded and shapes how the NEED is read later.',
        '',
        'Finding kinds, each about ONE agreed NEED, its subject:',
        '- VAGUE_TERM: the subject uses a word that cannot be checked as stated (quickly, unnecessary, eventually,',
        '  user-friendly). Quote the word and say what is left open.',
        '- SOLUTION_STATEMENT: the subject prescribes a solution - a technology, a design, a mechanism - instead of',
        '  stating a need.',
        '- SYSTEM_VOICE: the subject is worded as what a system shall do, not as what the stakeholder needs. An',
        '  ENVIRONMENT_FACT or a SCOPE_LIMITER states a fact or a limit: report its voice only when it claims what the',
        '  system shall do.',
        '- NOT_SINGULAR: the subject states more than one need.',
        '- REDUNDANCY: another agreed NEED already says what the subject says, wholly or in part. Name it as counterpart.',
        '',
        'Rules:',
        '- Report only what holds. No finding at all is a valid answer.',
        '- A subject is the reqId of one agreed NEED listed below; a counterpart is another listed NEED, exactly as',
        '  written there.',
        '- Each finding\'s text says what is wrong in one or two sentences, quoting the words concerned.',
        '- Two NEEDs that cannot both hold are not a quality matter: do not report them here.',
        '',
    ]
    return '\n'.join(lines + cv.KIND_HINT + [''] + cv.corpus(needs) + cv.answer())
