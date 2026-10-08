# The NEED wording (plan 045, Phase 8): the prompt that asks CC to word ONE amendment of an agreed NEED as a person's
# instruction says, in the stakeholder's voice, and the check of CC's answer. CC only words: the decision to change the
# NEED is a person's, and so is the final text - the person submits it in a CC_WORDING decision, edited or not, and
# that submitted text is what is written to RG. CC's answer is a suggestion and nothing more.
#
# The answer is ONE JSON object {"title", "statement"}:
#   title      the amended NEED's title - one line, at most TITLE_MAX_CHARS characters
#   statement  the amended NEED's whole statement - not a diff, not the changed sentence alone
# The check is structural: both present, text a NEED item can take. The voice is the prompt's job. The Dispatcher's
# mhdg-nrvv.finish-run reads the same answer again before it records it (NrvvWordingUtils.parseSuggestion): a bad
# answer fails HERE, at the check Task, where resetting the CC Task repairs it.
#
# Pure: no I/O.

import json

import nrvv_assessment as na

TITLE_MAX_CHARS = 250
FIELDS = ('title', 'statement')


def request_of(raw):
    """What the run words (NrvvWordingUtils.wordingRequestJson): {"targetNeedReqId", "instruction"}, or a ValueError."""
    try:
        data = json.loads(raw or '')
    except ValueError:
        raise ValueError('the wording request is not JSON: ' + na.excerpt(raw)) from None
    if (not isinstance(data, dict) or not str(data.get('targetNeedReqId') or '').strip()
            or not str(data.get('instruction') or '').strip()):
        raise ValueError('the wording request has no targetNeedReqId or no instruction: ' + na.excerpt(raw))
    return data


def target_of(request, agreed_needs):
    """The agreed NEED the request targets, or a ValueError when it is not among the NEEDs at the run's snapshot."""
    target = str(request.get('targetNeedReqId')).strip()
    for n in agreed_needs:
        if str(n.get('reqId')) == target:
            return n
    raise ValueError('the target NEED ' + repr(target) + ' is not one of the agreed NEEDs at the run\'s snapshot')


def compose(proposal, request, agreed_needs):
    """The wording prompt: amend the target NEED as the instruction says, in light of the proposal."""
    target = target_of(request, agreed_needs)
    source = proposal.get('source') or {}
    lines = [
        'You word ONE amendment of a stakeholder NEED that a project has already agreed.',
        '',
        'A person has decided that this NEED changes, and has written an instruction saying how. You do not decide,',
        'evaluate or argue with that decision: you only word the amended NEED as the instruction asks.',
        '',
        'How a NEED is worded:',
        '- The subject is the stakeholder, never a system: "The pricing team needs ...", not "The system shall ...".',
        '- It states what is needed, not a solution: no technology, design, component or mechanism.',
        '- Every term can be checked as stated: keep measurable terms exactly as the instruction or the NEED gives them',
        '  (a number with its unit stays that number with that unit) and never introduce a vague one.',
        '',
        'Rules:',
        '- Keep the current NEED\'s text wherever the instruction does not ask for a change; change only what it asks.',
        '- Answer with the whole amended statement, not a difference and not the changed sentence alone.',
        '- Keep the current title unless the change makes it wrong; a title is one line of at most '
        + str(TITLE_MAX_CHARS) + ' characters.',
        '- The amended NEED must not contradict the other agreed NEEDs listed below.',
        '- Never add a commentary, an explanation or an alternative.',
        '',
        'Store your answer with the result tool as exactly this JSON object, and nothing else:',
        '{"title": "<the amended title>", "statement": "<the whole amended statement>"}',
        '',
        'The NEED to amend, ' + str(target.get('reqId')) + ' (revision ' + str(target.get('revision')) + '):',
        'Title: ' + str(target.get('title') or '').strip(),
        'Statement:',
        str(target.get('statement') or '').strip(),
        '',
        'The proposal the change answers, ' + str(proposal.get('ref') or '') + ':',
        'Title: ' + str(proposal.get('title')).strip(),
        'Statement: ' + str(proposal.get('statement')).strip(),
    ]
    if source.get('stakeholder'):
        lines.append('Stated by: ' + str(source.get('stakeholder')))
    if source.get('text'):
        lines.append('In their words: ' + str(source.get('text')))
    lines.append('')
    lines.append('The person\'s instruction:')
    lines.append(str(request.get('instruction')).strip())
    others = [n for n in agreed_needs if str(n.get('reqId')) != str(target.get('reqId'))]
    lines.append('')
    if not others:
        lines.append('The project has no other agreed NEED.')
    else:
        lines.append('The other agreed NEEDs:')
        for n in others:
            lines.append('')
            lines.append(str(n.get('reqId')) + ' (revision ' + str(n.get('revision')) + '): ' + str(n.get('title') or '').strip())
            lines.append(str(n.get('statement') or '').strip())
    return '\n'.join(lines)


def wording_of(cc_result):
    """CC's suggestion as the canonical answer {"title", "statement"}, both stripped, or a ValueError."""
    text = (cc_result or '').strip()
    fenced = na.FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError('CC answered something that is not JSON: ' + na.excerpt(text)) from None
    if not isinstance(data, dict):
        raise ValueError('CC answered no {"title", "statement"} object: ' + na.excerpt(text))
    extra = [k for k in data.keys() if k not in FIELDS]
    if extra:
        raise ValueError('the answer has an unknown field ' + repr(extra[0]))
    title = data.get('title')
    statement = data.get('statement')
    if not isinstance(title, str) or not title.strip():
        raise ValueError('the answer has no title')
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError('the answer has no statement')
    title = title.strip()
    if '\n' in title or '\r' in title:
        raise ValueError('the title is not one line: ' + na.excerpt(title))
    if len(title) > TITLE_MAX_CHARS:
        raise ValueError('the title is longer than ' + str(TITLE_MAX_CHARS) + ' characters')
    return {'title': title, 'statement': statement.strip()}
