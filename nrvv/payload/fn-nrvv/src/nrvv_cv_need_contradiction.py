# NEED check CONTRADICTION (plan 047, Phase 10): pairs of agreed NEEDs that cannot both hold. A CONTRADICTION is a hard
# finding: while one stands open NRVV declines to produce a solution (decision 11). Run 3 times per gate, the union of
# the attempts deduplicated by conflict key (decision 13).
#
# Pure: the prompt and the kinds. The Task runners are nrvv_cv_need_contradiction_prompt.py / _check.py.

import nrvv_cv_need as cv

KINDS = ('CONTRADICTION',)
PAIR_KINDS = ('CONTRADICTION',)


def compose(needs):
    """The contradiction prompt over the agreed NEEDs."""
    lines = [
        'You check the NEEDs a project\'s stakeholders have agreed for contradictions: pairs of NEEDs that cannot both',
        'hold.',
        '',
        'Two NEEDs contradict when NO design can satisfy both: in some situation the world can actually present, meeting',
        'one NEED violates the other. For every such pair report one CONTRADICTION, with one NEED as subject and the other',
        'as counterpart. Its text gives the minimal witness situation - the concrete situation in which the two cannot',
        'both hold - in two or three sentences, quoting the words of both NEEDs concerned.',
        '',
        'Not a contradiction - do not report:',
        '- a tension a design can reconcile: both can hold at once in every situation, at some cost;',
        '- a COST_OBJECTIVE NEED against any other NEED: costs are weighed against each other, they never contradict;',
        '- a vague or ambiguous word: that is a quality matter, judged elsewhere;',
        '- an OBLIGATION that is hard to meet under an ENVIRONMENT_FACT but still possible.',
        '',
        'Report each pair once. No finding at all is a valid answer: report only what holds.',
        '',
    ]
    return '\n'.join(lines + cv.KIND_HINT + [''] + cv.corpus(needs) + cv.answer())
