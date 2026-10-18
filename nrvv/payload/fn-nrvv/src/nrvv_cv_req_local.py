"""Requirement check LOCAL_CONTRADICTION: can a changed requirement hold together with each of the requirements near it?
One CC session per subject judges it against its candidates only - its parent, siblings and children, the items it reads
under, the requirements citing the NEEDs it cites, the Interface and Environment items, then the requirements sharing the
most words with it - never against the whole set. It names every candidate that cannot hold together with it, each with
a witness situation; each one becomes a hard REQ_CONTRADICTION.

The context is mhdg-nrvv.read-local-cv-input's `localCvContext`:
  {"subjects": [{"reqId", "section", "title", "statement", "rationale",
                 "candidates": [{"reqId", "why", "section", "title", "statement"}]}]}
The chunk is one reqId (mh.batch-line-splitter over the output `subjects`, one line per Task).

The canonical answer is {"subject": "<reqId>", "contradictions": [{"counterpart", "text"}]} - an empty list when the
subject holds together with every candidate. A check that refuses CC's answer writes
{"refused": "<rule>", "subjects": [<the subject>]} and its Task succeeds: mhdg-nrvv.store-findings records the refusal and
the run goes on. A chunk that does not name exactly one subject of the context is a defect of the flow, not of the answer:
its ValueError fails the Task. The Dispatcher checks the same rules again.

Pure apart from run_prompt / run_check.
"""

import json

import mh_task_io as io
import nrvv_assessment as na
import nrvv_cc_answer as ca
import nrvv_cv_need as cv

FIELDS = ('subject', 'contradictions')
CONTRADICTION_FIELDS = ('counterpart', 'text')

SECTION_NAMES = {
    'NRVV:INTERPRETATION': 'interpretation item',
    'NRVV:INTERFACE': 'Interface item',
    'NRVV:ENVIRONMENT': 'Environment item',
}

ANSWER_SHAPE = ('{"subject": "<the reqId judged>", "contradictions": [{"counterpart": "<candidate reqId>", '
                '"text": "<the situation in which the two cannot both hold>"}]}')


def context_of(raw):
    """The LOCAL_CONTRADICTION context (mhdg-nrvv.read-local-cv-input), or a ValueError."""
    try:
        data = json.loads(raw or '')
    except ValueError:
        raise ValueError('the local contradiction context is not JSON: ' + na.excerpt(raw)) from None
    if not isinstance(data, dict) or not isinstance(data.get('subjects'), list):
        raise ValueError('the local contradiction context has no subjects list: ' + na.excerpt(raw))
    for s in data['subjects']:
        if not isinstance(s, dict) or not s.get('reqId') or not isinstance(s.get('candidates', []), list):
            raise ValueError('the local contradiction context has a subject with no reqId or no candidates list')
    return data


def subject_of(raw, context):
    """The one subject of a chunk - a subject of the context - or a ValueError."""
    ids = [line.strip() for line in (raw or '').splitlines() if line.strip()]
    if len(ids) != 1:
        raise ValueError('the chunk names ' + str(len(ids)) + ' subjects: a LOCAL_CONTRADICTION chunk is one requirement')
    subjects = {str(s['reqId']): s for s in context['subjects']}
    if ids[0] not in subjects:
        raise ValueError('the chunk names ' + repr(ids[0]) + ', which is not a subject of the local contradiction context')
    return subjects[ids[0]]


def _label(r):
    section = r.get('section')
    if not section:
        return ''
    return SECTION_NAMES.get(str(section), 'in section ' + str(section))


def _block(lines, indent, text):
    for text_line in str(text or '').strip().splitlines():
        lines.append(indent + text_line)


def compose(subject):
    """The LOCAL_CONTRADICTION prompt for one subject of the context. The answer instruction is the LAST part."""
    lines = [
        'You judge whether one requirement of a project can hold together with each of the requirements near it.',
        '',
        'Two requirements contradict when there is a situation the world can present in which meeting one of them makes',
        'meeting the other impossible. For the requirement under "Requirement to judge", name every candidate listed',
        'under "Candidates" that contradicts it, each with such a situation.',
        '',
        'Rules:',
        '- Judge contradiction only. Two requirements that overlap, repeat each other, use other words or state more or',
        '  less detail do not contradict; neither does a requirement that obliges something the other does not mention.',
        '- A requirement derived under another one refines it: being more specific is no contradiction. It contradicts',
        '  its parent only when meeting it makes the parent impossible to meet.',
        '- An interpretation item states how the NEEDs are read: an ASSUMPTION states how the world behaves, a READING how',
        '  an obligation is read, an OPEN_CHOICE what the NEEDs leave open. A requirement contradicts an ASSUMPTION when it',
        '  can be met only if the world behaves otherwise, a READING when it demands what the reading rules out, an',
        '  OPEN_CHOICE when it fixes the dimension the item leaves open.',
        '- An Environment item states what the tests simulate of the world; an Interface item states the boundary of the',
        '  system.',
        '- Name only candidates, each once, by its reqId exactly as written. The text describes the situation and why the',
        '  two cannot both hold, quoting the words of both.',
        '- When the requirement holds together with every candidate, the list is empty.',
        '',
    ]
    req_id = str(subject['reqId'])
    label = _label(subject)
    lines.append('Requirement to judge: ' + req_id + (' (' + label + ')' if label else '') + ': '
                 + str(subject.get('title') or '').strip())
    _block(lines, '  ', subject.get('statement'))
    rationale = str(subject.get('rationale') or '').strip()
    if rationale:
        lines.append('  Rationale: ' + rationale.replace('\n', ' | '))
    lines.append('')
    candidates = subject.get('candidates') or []
    if candidates:
        lines.append('Candidates:')
        for c in candidates:
            lines.append('')
            label = _label(c)
            lines.append('Candidate ' + str(c.get('reqId')) + ' (' + str(c.get('why') or 'near')
                         + (', ' + label if label else '') + '): ' + str(c.get('title') or '').strip())
            _block(lines, '  ', c.get('statement'))
    else:
        lines.append('Candidates: none - the list of contradictions is empty.')
    return '\n'.join(lines + [
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object - the subject as',
        'written above, one entry per contradicting candidate - and nothing else:',
        ANSWER_SHAPE,
        cv.ANSWER_TAIL.replace('the findings', 'the contradictions'),
    ])


def contradictions_of(cc_result, subject):
    """CC's answer as the canonical {"subject", "contradictions": [...]}, or a ValueError naming the first broken rule."""
    text = (cc_result or '').strip()
    fenced = na.FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    data = ca.loads(text)
    if not isinstance(data, dict) or set(data.keys()) != set(FIELDS) or not isinstance(data['contradictions'], list):
        raise ValueError('CC answered no {"subject": ..., "contradictions": [...]} object: ' + na.excerpt(text))
    req_id = str(subject['reqId'])
    named = str(data.get('subject') or '').strip()
    if named != req_id:
        raise ValueError('CC answered on ' + repr(named) + ', not on the requirement judged ' + req_id)
    candidates = {str(c.get('reqId')) for c in subject.get('candidates') or []}
    out = []
    seen = set()
    for i, c in enumerate(data['contradictions']):
        where = 'contradiction #' + str(i)
        if not isinstance(c, dict):
            raise ValueError(where + ' is not an object')
        extra = [k for k in c.keys() if k not in CONTRADICTION_FIELDS]
        if extra:
            raise ValueError(where + ' has an unknown field ' + repr(extra[0]))
        counterpart = str(c.get('counterpart') or '').strip()
        if counterpart not in candidates:
            raise ValueError(where + ' names ' + repr(counterpart) + ', which is not a candidate of ' + req_id)
        if counterpart in seen:
            raise ValueError(where + ' names ' + counterpart + ' a second time')
        seen.add(counterpart)
        reason = c.get('text')
        if reason is not None and not isinstance(reason, str):
            raise ValueError(where + ' has a text that is not a string')
        reason = (reason or '').strip()
        if not reason:
            raise ValueError(where + ' (' + counterpart + ') names no situation in which the two cannot both hold')
        out.append({'counterpart': counterpart, 'text': reason})
    return {'subject': req_id, 'contradictions': out}


def checked(cc_result, context, chunk):
    """The checked answer, or {"refused": "<rule>", "subjects": [<the subject>]} when CC's answer breaks a rule. A chunk
    that is not exactly one subject of the context is a defect of the flow: subject_of's ValueError fails the Task."""
    subject = subject_of(chunk, context)
    try:
        return contradictions_of(cc_result, subject)
    except ValueError as e:
        return {'refused': str(e), 'subjects': [str(subject['reqId'])]}


def run_prompt(task, function_code):
    context = context_of(io.read_role(task, 'local-cv-context'))
    subject = subject_of(io.read_role(task, 'subjects'), context)
    prompt = compose(subject)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(function_code + ': ' + str(subject['reqId']) + ', ' + str(len(subject.get('candidates') or [])) + ' candidate(s), '
          + str(len(prompt)) + ' chars')


def run_check(task, function_code):
    context = context_of(io.read_role(task, 'local-cv-context'))
    answer = checked(io.read_role(task, 'cc-result'), context, io.read_role(task, 'subjects'))
    io.write_text(io.output_role(task, 'findings'), json.dumps(answer, ensure_ascii=False))
    if 'refused' in answer:
        print(function_code + ': ' + answer['subjects'][0] + ' REFUSED: ' + ca.excerpt(answer['refused']))
    else:
        print(function_code + ': ' + answer['subject'] + ', ' + str(len(answer['contradictions'])) + ' contradiction(s): '
              + ', '.join(c['counterpart'] for c in answer['contradictions']))
