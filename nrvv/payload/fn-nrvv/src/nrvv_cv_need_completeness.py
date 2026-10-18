"""NEED check COMPLETENESS (INCOSE C10): per derivation NEED, do its top-level requirements, read under the items
that govern it, guarantee what the NEED requires? One CC session per chunk of at most 10 NEEDs answers, per NEED,
exactly one verdict:
  MET       the requirements guarantee what the NEED requires                                     - no finding
  NOT_MET   text: a situation in which every requirement of the NEED is met and what the NEED
            requires still does not hold, or the NEED has no requirement                          - hard

The context is mhdg-nrvv.read-completeness-input's `completenessContext`:
  {"subjects": [{"need": {"reqId", "revision", "kind", "title", "statement"},
                 "readings": [{"reqId", "kind", "statement"}],
                 "requirements": [{"reqId", "title", "statement", "rationale"}]}]}
The chunk is one NEED reqId per line (mh.batch-line-splitter over the output `subjects`).

The canonical answer {"verdicts": [{"subject", "verdict", "text"?}]} has exactly one entry per NEED of the chunk, in
chunk order. A check that refuses CC's answer writes {"refused": "<rule>", "subjects": [<the chunk>]} and its Task
succeeds: mhdg-nrvv.store-findings records the refusal per NEED of the chunk, and the run goes on. A chunk naming a NEED
the context does not hold is a defect of the flow, not of the answer: its ValueError fails the Task. The Dispatcher
checks the same rules again.

Pure apart from run_prompt / run_check.
"""

import json

import mh_task_io as io
import nrvv_assessment as na
import nrvv_cc_answer as ca
import nrvv_cv_need as cv

VERDICTS = ('MET', 'NOT_MET')
FIELDS = ('subject', 'verdict', 'text')
CHUNK_SIZE = 10

ANSWER_SHAPE = ('{"verdicts": [{"subject": "<NEED reqId>", "verdict": "<MET|NOT_MET>", '
                '"text": "<for NOT_MET: the situation>"}]}')


def context_of(raw):
    """The COMPLETENESS context (mhdg-nrvv.read-completeness-input), or a ValueError."""
    try:
        data = json.loads(raw or '')
    except ValueError:
        raise ValueError('the completeness context is not JSON: ' + na.excerpt(raw)) from None
    if not isinstance(data, dict) or not isinstance(data.get('subjects'), list):
        raise ValueError('the completeness context has no subjects list: ' + na.excerpt(raw))
    for s in data['subjects']:
        if not isinstance(s, dict) or not isinstance(s.get('need'), dict) or not s['need'].get('reqId'):
            raise ValueError('the completeness context has a subject with no NEED reqId')
    return data


def chunk_of(raw, context):
    """The NEEDs of one chunk - one reqId per line, each a subject of the context - or a ValueError."""
    known = {str(s['need']['reqId']) for s in context['subjects']}
    ids = [line.strip() for line in (raw or '').splitlines() if line.strip()]
    if not ids:
        raise ValueError('the chunk names no subject')
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ValueError('the chunk names ' + repr(unknown[0]) + ', which is not a subject of the completeness context')
    if len(set(ids)) != len(ids):
        raise ValueError('the chunk names a subject twice')
    return ids


def _block(lines, indent, text):
    for text_line in str(text or '').strip().splitlines():
        lines.append(indent + text_line)


def compose(context, chunk):
    """The COMPLETENESS prompt for the NEEDs `chunk` of `context`. The answer instruction is the LAST part."""
    subjects = {str(s['need']['reqId']): s for s in context['subjects']}
    lines = [
        'You judge whether a project\'s requirements are complete against the NEEDs its stakeholders have agreed: for',
        'each NEED listed, do its top-level requirements, read under the items that govern it, guarantee what the NEED',
        'requires?',
        '',
        'A NEED states what a stakeholder needs, in the stakeholder\'s words. A requirement states what the system shall',
        'do. A READING item states how the NEED is read together with the NEEDs that qualify it; an OPEN_CHOICE item',
        'names a dimension the NEEDs leave open. Both govern the NEED: judge the NEED as its governing items read it.',
        '',
        'For EACH NEED listed under "NEEDs to judge", give exactly one verdict:',
        '- MET: in every situation the world can present, meeting all of the NEED\'s requirements gives what the NEED,',
        '  read under its governing items, requires.',
        '- NOT_MET: there is a situation in which every requirement of the NEED is met and what the NEED requires still',
        '  does not hold - or the NEED has no requirement. The text describes that situation and quotes the words of',
        '  the NEED it leaves unmet.',
        '',
        'Rules:',
        '- Judge completeness only: whether the requirements guarantee what the NEED requires. Do not judge the wording,',
        '  and do not judge whether a requirement obliges more than its NEED - another check judges that.',
        '- A COST_OBJECTIVE NEED is an objective to weigh, never a fixed bound: requirements that measure and report the',
        '  cost meet it. It is never NOT_MET because no requirement bounds the cost.',
        '- A dimension an OPEN_CHOICE item leaves open is not a gap: a NEED is never NOT_MET because no requirement',
        '  fixes that dimension.',
        '- An "ambiguity:" line of a Rationale records what the NEEDs leave open; it guarantees nothing.',
        '- One verdict per listed NEED, its reqId as subject, exactly as written. Never invent a requirement, never',
        '  rewrite one.',
        '',
    ]
    lines += cv.KIND_HINT + ['']
    lines.append('NEEDs to judge:')
    for req_id in chunk:
        s = subjects[req_id]
        n = s['need']
        kind = n.get('kind')
        lines.append('')
        lines.append('NEED ' + req_id + ' (revision ' + str(n.get('revision')) + (', ' + str(kind) if kind else '')
                     + '): ' + str(n.get('title') or '').strip())
        _block(lines, '  ', n.get('statement'))
        readings = s.get('readings') or []
        if readings:
            lines.append('  Governed by:')
            for r in readings:
                lines.append('    ' + str(r.get('kind') or 'READING') + ' ' + str(r.get('reqId')) + ': '
                             + ' '.join(str(r.get('statement') or '').split()))
        else:
            lines.append('  Governed by no item.')
        requirements = s.get('requirements') or []
        if requirements:
            lines.append('  Its top-level requirements:')
            for q in requirements:
                title = str(q.get('title') or '').strip()
                lines.append('    Requirement ' + str(q.get('reqId')) + (': ' + title if title else ''))
                _block(lines, '      ', q.get('statement'))
                rationale = str(q.get('rationale') or '').strip()
                if rationale:
                    lines.append('      Rationale: ' + rationale.replace('\n', ' | '))
        else:
            lines.append('  No top-level requirement cites this NEED.')
    return '\n'.join(lines + [
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object - one entry per',
        'NEED listed, in the order listed - and nothing else:',
        ANSWER_SHAPE,
        cv.ANSWER_TAIL.replace('the findings', 'the verdicts'),
    ])


def verdicts_of(cc_result, chunk):
    """CC's verdicts as the canonical answer {"verdicts": [...]} in chunk order, or a ValueError naming the first
    broken rule."""
    text = (cc_result or '').strip()
    fenced = na.FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    data = ca.loads(text)
    if not isinstance(data, dict) or set(data.keys()) != {'verdicts'} or not isinstance(data['verdicts'], list):
        raise ValueError('CC answered no {"verdicts": [...]} object: ' + na.excerpt(text))
    wanted = set(chunk)
    by_subject = {}
    for i, v in enumerate(data['verdicts']):
        where = 'verdict #' + str(i)
        if not isinstance(v, dict):
            raise ValueError(where + ' is not an object')
        extra = [k for k in v.keys() if k not in FIELDS]
        if extra:
            raise ValueError(where + ' has an unknown field ' + repr(extra[0]))
        subject = str(v.get('subject') or '').strip()
        if subject not in wanted:
            raise ValueError(where + ' names subject ' + repr(subject) + ', which is not a NEED of this chunk')
        if subject in by_subject:
            raise ValueError(where + ' names ' + subject + ' a second time')
        where += ' (' + subject + ')'
        verdict = v.get('verdict')
        if verdict not in VERDICTS:
            raise ValueError(where + ' has an unknown verdict ' + repr(verdict))
        reason = v.get('text')
        if reason is not None and not isinstance(reason, str):
            raise ValueError(where + ' has a text that is not a string')
        reason = (reason or '').strip()
        if not reason and verdict == 'NOT_MET':
            raise ValueError(where + ' is NOT_MET and names no situation the NEED requires and its requirements do'
                             ' not guarantee')
        item = {'subject': subject, 'verdict': verdict}
        if reason:
            item['text'] = reason
        by_subject[subject] = item
    missing = [s for s in chunk if s not in by_subject]
    if missing:
        raise ValueError('CC gave no verdict on ' + ', '.join(missing) + ': every NEED of the chunk gets one')
    return {'verdicts': [by_subject[s] for s in chunk]}


def checked(cc_result, context, chunk):
    """The checked answer - the verdicts, or {"refused": "<rule>", "subjects": [<the chunk>]} when CC's answer breaks a
    rule. A chunk the context does not hold is a defect of the flow: chunk_of's ValueError fails the Task."""
    ids = chunk_of('\n'.join(chunk), context)
    try:
        return verdicts_of(cc_result, ids)
    except ValueError as e:
        return {'refused': str(e), 'subjects': list(ids)}


def run_prompt(task, function_code):
    context = context_of(io.read_role(task, 'completeness-context'))
    chunk = chunk_of(io.read_role(task, 'subjects'), context)
    prompt = compose(context, chunk)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(function_code + ': ' + str(len(chunk)) + ' NEED(s) of ' + str(len(context['subjects'])) + ', '
          + str(len(prompt)) + ' chars')


def run_check(task, function_code):
    context = context_of(io.read_role(task, 'completeness-context'))
    chunk = chunk_of(io.read_role(task, 'subjects'), context)
    answer = checked(io.read_role(task, 'cc-result'), context, chunk)
    io.write_text(io.output_role(task, 'findings'), json.dumps(answer, ensure_ascii=False))
    if 'refused' in answer:
        print(function_code + ': ' + str(len(chunk)) + ' NEED(s) REFUSED: ' + ca.excerpt(answer['refused']))
    else:
        print(function_code + ': ' + str(len(answer['verdicts'])) + ' verdict(s): '
              + ', '.join(v['verdict'] + '/' + v['subject'] for v in answer['verdicts']))
