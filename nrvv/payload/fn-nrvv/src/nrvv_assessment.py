# The NEED assessment (plan 045, Phase 7): the prompt that asks CC to assess ONE proposed NEED against the project's
# agreed NEEDs, and the check of CC's answer. CC produces findings only - never a decision: whether a proposal is
# ACCEPTED, RESOLVED_BY_AMENDMENT, COVERED or REJECTED is a person's call, taken in NRVV's UI.
#
# The answer is ONE JSON object {"findings": [{"kind", "counterpart"?, "text"}]}:
#   kind         one of KINDS
#   counterpart  the reqId of the agreed NEED a pair finding is about - required for CONTRADICTION and REDUNDANCY,
#                optional for the others; always one of the agreed NEEDs the run was given
#   text         what the finding is, in one or two sentences
# The Dispatcher's mhdg-nrvv.store-findings checks the same rules again before it writes (NrvvAssessmentUtils
# .parseFindings): a bad answer fails HERE, at the check Task, where resetting the CC Task repairs it.
#
# Pure: no I/O.

import json
import re

KINDS = ('CONTRADICTION', 'REDUNDANCY', 'VAGUE_TERM', 'SOLUTION_STATEMENT', 'SYSTEM_VOICE', 'NOT_SINGULAR')
PAIR_KINDS = ('CONTRADICTION', 'REDUNDANCY')
FIELDS = ('kind', 'counterpart', 'text')

# A model sometimes wraps JSON in a markdown fence. That, and only that, is unwrapped (as the criterion check does).
FENCE = re.compile(r'^```[A-Za-z]*\s*\n(.*)\n```$', re.DOTALL)
EXCERPT = 300


def excerpt(text):
    text = text or ''
    return text if len(text) <= EXCERPT else text[:EXCERPT] + '...'


def proposal_of(raw):
    """The proposal object the Dispatcher handed the run (NrvvAssessmentUtils.proposalJson), or a ValueError."""
    try:
        data = json.loads(raw or '')
    except ValueError:
        raise ValueError('the proposal is not JSON: ' + excerpt(raw)) from None
    if not isinstance(data, dict) or not str(data.get('title') or '').strip() or not str(data.get('statement') or '').strip():
        raise ValueError('the proposal has no title or no statement: ' + excerpt(raw))
    return data


def agreed_needs_of(raw):
    """The agreed NEEDs the run was given (NrvvAssessmentUtils.agreedNeedsJson) - a list, possibly empty."""
    try:
        data = json.loads(raw or '[]')
    except ValueError:
        raise ValueError('the agreed NEEDs are not JSON: ' + excerpt(raw)) from None
    if not isinstance(data, list) or any(not isinstance(n, dict) or not n.get('reqId') for n in data):
        raise ValueError('the agreed NEEDs are not a list of NEEDs with a reqId: ' + excerpt(raw))
    return data


def compose(proposal, agreed_needs):
    """The assessment prompt for `proposal` against `agreed_needs`."""
    source = proposal.get('source') or {}
    lines = [
        'You assess ONE proposed stakeholder NEED against the NEEDs a project has already agreed.',
        '',
        'A NEED states what a stakeholder needs, in the stakeholder\'s voice. You do not decide anything: a person',
        'decides whether the proposal is accepted, merged into an agreed NEED, already covered, or rejected. You only',
        'report findings, each about something the person must see before deciding.',
        '',
        'Finding kinds:',
        '- CONTRADICTION: the proposal and an agreed NEED cannot both hold. Name that NEED as counterpart.',
        '- REDUNDANCY: an agreed NEED already says what the proposal says, wholly or in part. Name it as counterpart.',
        '- VAGUE_TERM: the proposal uses a term that cannot be checked as stated (quickly, user-friendly, as needed).',
        '- SOLUTION_STATEMENT: the proposal prescribes a solution (a technology, a design, a mechanism) rather than',
        '  stating a need.',
        '- SYSTEM_VOICE: the proposal is worded as what a system shall do, not as what a stakeholder needs.',
        '- NOT_SINGULAR: the proposal states more than one need.',
        '',
        'Rules:',
        '- Report only what holds. No finding at all is a valid answer.',
        '- A counterpart is the reqId of one agreed NEED listed below, exactly as written there.',
        '- Each finding\'s text says what is wrong in one or two sentences, quoting the words concerned.',
        '- Never recommend an outcome and never rewrite the proposal.',
        '',
        'Store your answer with the result tool as exactly this JSON object, and nothing else:',
        '{"findings": [{"kind": "<kind>", "counterpart": "<reqId or null>", "text": "<what is wrong>"}]}',
        '',
        'The proposed NEED ' + str(proposal.get('ref') or '') + ':',
        'Title: ' + str(proposal.get('title')).strip(),
        'Statement: ' + str(proposal.get('statement')).strip(),
    ]
    if source.get('stakeholder'):
        lines.append('Stated by: ' + str(source.get('stakeholder')))
    if source.get('text'):
        lines.append('In their words: ' + str(source.get('text')))
    lines.append('')
    if not agreed_needs:
        lines.append('The project has no agreed NEED yet.')
    else:
        lines.append('The agreed NEEDs:')
        for n in agreed_needs:
            lines.append('')
            lines.append(str(n.get('reqId')) + ' (revision ' + str(n.get('revision')) + '): ' + str(n.get('title') or '').strip())
            lines.append(str(n.get('statement') or '').strip())
    return '\n'.join(lines)


def findings_of(cc_result, agreed_needs):
    """CC's findings as the canonical answer {"findings": [...]}, or a ValueError naming the first violation."""
    text = (cc_result or '').strip()
    fenced = FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError('CC answered something that is not JSON: ' + excerpt(text)) from None
    if not isinstance(data, dict) or set(data.keys()) != {'findings'} or not isinstance(data['findings'], list):
        raise ValueError('CC answered no {"findings": [...]} object: ' + excerpt(text))
    known = {str(n.get('reqId')) for n in agreed_needs}
    out = []
    for i, f in enumerate(data['findings']):
        if not isinstance(f, dict):
            raise ValueError('finding #' + str(i) + ' is not an object')
        extra = [k for k in f.keys() if k not in FIELDS]
        if extra:
            raise ValueError('finding #' + str(i) + ' has an unknown field ' + repr(extra[0]))
        kind = f.get('kind')
        if kind not in KINDS:
            raise ValueError('finding #' + str(i) + ' has an unknown kind ' + repr(kind))
        finding_text = f.get('text')
        if not isinstance(finding_text, str) or not finding_text.strip():
            raise ValueError('finding #' + str(i) + ' has no text')
        counterpart = f.get('counterpart')
        counterpart = None if counterpart is None else str(counterpart).strip() or None
        if counterpart is None and kind in PAIR_KINDS:
            raise ValueError('finding #' + str(i) + ' is a ' + kind + ' and names no counterpart')
        if counterpart is not None and counterpart not in known:
            raise ValueError('finding #' + str(i) + ' names counterpart ' + repr(counterpart)
                             + ', which is not one of the agreed NEEDs')
        item = {'kind': kind, 'text': finding_text.strip()}
        if counterpart is not None:
            item['counterpart'] = counterpart
        out.append(item)
    return {'findings': out}
