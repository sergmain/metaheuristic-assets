# NEED check BACKTRACE (plan 047, Phase 17): back-validation - is every requirement in force justified by the NEEDs in
# force? The subjects are every owned top-level requirement (read at its live row) and every ACTIVE member of the live
# IMPOSED held sections; one CC session per chunk of at most 40 of them answers, per subject, exactly one verdict
# (decision 8):
#   JUSTIFIED            needReqIds: the agreed NEEDs that justify it (at least one)                        - no finding
#   OVER_REACH           an owned requirement obliges something no agreed NEED states; text: that obligation - hard
#   CONTRADICTS_NEED     needReqId: the agreed NEED it violates; text: the situation                         - hard
#   RESTS_ON_SUPERSEDED  needReqId: a NEED the subject cites at a revision no longer in force; text: the
#                        superseded words it rests on                                                        - hard
#   UNNEEDED             a held requirement no agreed NEED needs; text: why                                  - soft
# OVER_REACH is an owned requirement's verdict and UNNEEDED a held one's: an imposed requirement no NEED asks for is not
# an over-reach of this project's definition, and it is not resolved by re-defining it.
#
# The context is mhdg-nrvv.read-backtrace-input's output (NrvvData.BacktraceContext as JSON):
#   {"snapshotId", "needs": [{"reqId", "revision", "title", "statement", "kind"}],
#    "subjects": [{"reqId", "liveReqId", "held", "sectionReqId", "title", "statement", "rationale", "citations",
#                  "superseded": [{"needReqId", "revision", "title", "statement"}], "tracedFrom"}]}
# The chunk is one reqId per line (mh.batch-line-splitter over the output `subjects`).
#
# The canonical answer {"verdicts": [{"subject", "verdict", "needReqIds"?, "needReqId"?, "text"}]} has exactly one entry
# per subject of the chunk, in chunk order, and only the fields its verdict uses. Every verdict but JUSTIFIED gives its
# text - it is the finding stored; a JUSTIFIED one stores nothing, so its text is optional (kept when given). The
# Dispatcher's mhdg-nrvv.store-findings checks the same rules again (NrvvFindingUtils.parseBacktrace) and stores one
# finding per verdict other than JUSTIFIED.
#
# Pure but for run_prompt() / run_check().

import json

import mh_task_io as io
import nrvv_assessment as na
import nrvv_cc_answer as ca
import nrvv_cv_need as cv

VERDICTS = ('JUSTIFIED', 'OVER_REACH', 'CONTRADICTS_NEED', 'RESTS_ON_SUPERSEDED', 'UNNEEDED')
FIELDS = ('subject', 'verdict', 'needReqIds', 'needReqId', 'text')
CHUNK_SIZE = 40

ANSWER_SHAPE = ('{"verdicts": [{"subject": "<requirement reqId>", '
                '"verdict": "<JUSTIFIED|OVER_REACH|CONTRADICTS_NEED|RESTS_ON_SUPERSEDED|UNNEEDED>", '
                '"needReqIds": ["<NEED reqId>"], "needReqId": "<NEED reqId or null>", "text": "<why>"}]}')


def context_of(raw):
    """The back-validation context (mhdg-nrvv.read-backtrace-input: NrvvData.BacktraceContext), or a ValueError."""
    try:
        data = json.loads(raw or '')
    except ValueError:
        raise ValueError('the back-validation context is not JSON: ' + na.excerpt(raw)) from None
    if not isinstance(data, dict) or any(not isinstance(data.get(k), list) for k in ('needs', 'subjects')):
        raise ValueError('the back-validation context has no needs and subjects lists: ' + na.excerpt(raw))
    for k in ('needs', 'subjects'):
        if any(not isinstance(x, dict) or not x.get('reqId') for x in data[k]):
            raise ValueError('the back-validation context has an entry of ' + k + ' with no reqId')
    return data


def chunk_of(raw, context):
    """The subjects of one chunk - one reqId per line, each a subject of the context - or a ValueError."""
    known = {str(s['reqId']) for s in context['subjects']}
    ids = [line.strip() for line in (raw or '').splitlines() if line.strip()]
    if not ids:
        raise ValueError('the chunk names no subject')
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ValueError('the chunk names ' + repr(unknown[0]) + ', which is not a subject of the back-validation context')
    if len(set(ids)) != len(ids):
        raise ValueError('the chunk names a subject twice')
    return ids


def _superseded_needs(subject):
    return {str(x.get('needReqId')) for x in (subject.get('superseded') or []) if x.get('needReqId')}


def compose(context, chunk):
    """The back-validation prompt for the subjects `chunk` of `context`. The answer instruction is the LAST part."""
    subjects = {str(s['reqId']): s for s in context['subjects']}
    lines = [
        'You back-validate requirements against the NEEDs a project\'s stakeholders have agreed: is every requirement in',
        'force justified by the NEEDs in force?',
        '',
        'A NEED states what a stakeholder needs, in the stakeholder\'s words. A requirement states what the system shall',
        'do. A requirement is justified when every obligation it states is stated by an agreed NEED, or holds under every',
        'reading of the agreed NEEDs. Two kinds of requirement are judged: OWNED requirements this project defined from',
        'its NEEDs, and HELD requirements another party imposes on the project, which it must comply with.',
        '',
        'For EACH requirement listed under "Requirements to judge", give exactly one verdict:',
        '- JUSTIFIED: the agreed NEEDs state everything the requirement obliges. needReqIds names every agreed NEED it',
        '  rests on (at least one).',
        '- OVER_REACH (owned requirements only): the requirement obliges something no agreed NEED states - a number, a',
        '  duration, a rate, a limit or a behaviour the NEEDs never mention or leave open. The text quotes that obligation',
        '  from the requirement.',
        '- CONTRADICTS_NEED: in some situation the world can actually present, meeting the requirement violates an agreed',
        '  NEED. needReqId names that NEED; the text gives the situation, quoting the words of both.',
        '- RESTS_ON_SUPERSEDED: the requirement cites a NEED revision that is no longer in force (shown under it as "no',
        '  longer in force"), and what it obliges follows from that old text but not from the NEED as it reads now.',
        '  needReqId names that NEED; the text quotes the superseded words it rests on.',
        '- UNNEEDED (held requirements only): no agreed NEED needs what the held requirement obliges. The text says what',
        '  it obliges that nothing asks for.',
        '',
        'Rules:',
        '- Judge against the NEEDs as they read now, at the revision listed. Citing an old revision is not by itself a',
        '  verdict: when the NEED as it reads now still justifies the requirement, it is JUSTIFIED.',
        '- A requirement to measure and report a cost is justified by a COST_OBJECTIVE NEED; a fixed bound on that cost',
        '  is not - a COST_OBJECTIVE is an objective to weigh, never a bound.',
        '- An "ambiguity:" line of a Rationale records what the NEEDs leave open; it obliges nothing.',
        '- "Traced from" names the NEEDs a person or the definition linked to the requirement; it is a claim to check, not',
        '  a verdict.',
        '- An interpretation item is judged by its kind.',
        '  An ASSUMPTION is JUSTIFIED when a NEED it cites states the fact it states, and OVER_REACH when it assumes more than the NEEDs state.',
        '  A READING or an OPEN_CHOICE is OVER_REACH when it adds an obligation no NEED states or narrows what the NEEDs allow,',
        '  and JUSTIFIED when it reads the NEEDs it cites together without adding to them.',
        '- A requirement is judged together with the items it is read under and its evidence quotes: what such an item',
        '  says the NEEDs mean is what the requirement may oblige, and a quote shows the NEED words a clause rests on.',
        '- One verdict per listed requirement, its reqId as subject, exactly as written. Never invent a NEED, never',
        '  rewrite a requirement.',
        '',
    ]
    lines += cv.KIND_HINT + ['']
    if context['needs']:
        lines.append('The agreed NEEDs, as they read now:')
        for n in context['needs']:
            kind = n.get('kind')
            lines.append('')
            lines.append('NEED ' + str(n['reqId']) + ' (revision ' + str(n.get('revision'))
                         + (', ' + str(kind) if kind else '') + '): ' + str(n.get('title') or '').strip())
            for text_line in str(n.get('statement') or '').strip().splitlines():
                lines.append('  ' + text_line)
    else:
        lines.append('The project has no agreed NEED.')
    lines.append('')
    lines.append('Requirements to judge:')
    for req_id in chunk:
        s = subjects[req_id]
        lines.append('')
        if s.get('held'):
            lines.append('Held requirement ' + req_id + ' (imposed through section ' + str(s.get('sectionReqId'))
                         + ' - JUSTIFIED, CONTRADICTS_NEED or UNNEEDED):')
        else:
            live = s.get('liveReqId')
            name = req_id if not live or live == req_id else req_id + ' (now ' + str(live) + ')'
            kind = s.get('interpretationKind')
            if kind:
                lines.append('Interpretation item ' + name + ' (' + str(kind) + ' - JUSTIFIED, OVER_REACH, CONTRADICTS_NEED or'
                             + ' RESTS_ON_SUPERSEDED):')
            else:
                lines.append('Owned requirement ' + name + ' (top-level - JUSTIFIED, OVER_REACH, CONTRADICTS_NEED or'
                             + ' RESTS_ON_SUPERSEDED):')
        title = str(s.get('title') or '').strip()
        if title:
            lines.append('    Title: ' + title)
        for text_line in str(s.get('statement') or '').strip().splitlines():
            lines.append('    ' + text_line)
        rationale = str(s.get('rationale') or '').strip()
        if rationale:
            lines.append('    Rationale: ' + rationale.replace('\n', ' | '))
        governs = s.get('governs') or []
        if governs:
            lines.append('    Governs: ' + ', '.join(str(x) for x in governs))
        for r in s.get('readings') or []:
            lines.append('    Read under: ' + str(r.get('kind') or 'item') + ' ' + str(r.get('reqId')) + ': '
                         + ' '.join(str(r.get('statement') or '').split()))
        for e in s.get('evidence') or []:
            lines.append('    Evidence: ' + str(e.get('source')) + ' "' + str(e.get('quote') or '') + '"')
        traced = s.get('tracedFrom') or []
        lines.append('    Traced from: ' + (', '.join(str(x) for x in traced) if traced else 'no NEED'))
        for x in s.get('superseded') or []:
            old = ': '.join(p for p in (str(x.get('title') or '').strip(), str(x.get('statement') or '').strip()) if p)
            lines.append('    Cites ' + str(x.get('needReqId')) + ' r' + str(x.get('revision')) + ', no longer in force'
                         + (' - it read then: ' + old if old else ' - its text is not on the project\'s line'))
    return '\n'.join(lines + [
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object - one entry per',
        'requirement listed, in the order listed, with only the fields its verdict uses - and nothing else:',
        ANSWER_SHAPE,
        cv.ANSWER_TAIL.replace('the findings', 'the verdicts'),
    ])


def _ids(value):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        return None
    return [x.strip() for x in value]


def verdicts_of(cc_result, context, chunk):
    """CC's verdicts as the canonical answer {"verdicts": [...]} in chunk order, or a ValueError naming the first violation."""
    text = (cc_result or '').strip()
    fenced = na.FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    data = ca.loads(text)
    if not isinstance(data, dict) or set(data.keys()) != {'verdicts'} or not isinstance(data['verdicts'], list):
        raise ValueError('CC answered no {"verdicts": [...]} object: ' + na.excerpt(text))
    agreed = {str(n['reqId']) for n in context['needs']}
    subjects = {str(s['reqId']): s for s in context['subjects']}
    wanted = set(chunk)
    # plan 047 Phase 28: the prompt lists a requirement read at its live row as "<reqId> (now <liveReqId>)" - a
    # verdict naming the live reqId is the verdict on that subject
    live_of = {str(subjects[r].get('liveReqId')): r for r in chunk
               if subjects[r].get('liveReqId') and str(subjects[r].get('liveReqId')) != r}
    by_subject = {}
    for i, v in enumerate(data['verdicts']):
        where = 'verdict #' + str(i)
        if not isinstance(v, dict):
            raise ValueError(where + ' is not an object')
        extra = [k for k in v.keys() if k not in FIELDS]
        if extra:
            raise ValueError(where + ' has an unknown field ' + repr(extra[0]))
        subject = str(v.get('subject') or '').strip()
        subject = live_of.get(subject, subject)
        if subject not in wanted:
            raise ValueError(where + ' names subject ' + repr(subject) + ', which is not a requirement of this chunk')
        if subject in by_subject:
            raise ValueError(where + ' names ' + subject + ' a second time')
        where += ' (' + subject + ')'
        verdict = v.get('verdict')
        if verdict not in VERDICTS:
            raise ValueError(where + ' has an unknown verdict ' + repr(verdict))
        reason = v.get('text')
        if reason is not None and not isinstance(reason, str):
            raise ValueError(where + ' has a text that is not a string')
        # development run 244: a JUSTIFIED verdict stores nothing, so CC may leave its text out
        reason = (reason or '').strip()
        if not reason and verdict != 'JUSTIFIED':
            raise ValueError(where + ' has no text')
        ids = _ids(v.get('needReqIds'))
        if ids is None:
            raise ValueError(where + ' has needReqIds that is not a list of reqIds')
        need = v.get('needReqId')
        if need is not None and not isinstance(need, str):
            raise ValueError(where + ' has a needReqId that is not a reqId')
        need = (need or '').strip() or None
        held = bool(subjects[subject].get('held'))
        if verdict == 'JUSTIFIED':
            if not ids:
                raise ValueError(where + ' is JUSTIFIED and names no NEED in needReqIds')
            unknown = [x for x in ids if x not in agreed]
            if unknown:
                raise ValueError(where + ' is JUSTIFIED by ' + repr(unknown[0]) + ', which is not one of the agreed NEEDs')
            if len(set(ids)) != len(ids):
                raise ValueError(where + ' names a NEED twice in needReqIds')
        elif ids:
            raise ValueError(where + ' is ' + verdict + ' and names needReqIds: only JUSTIFIED does')
        if verdict == 'CONTRADICTS_NEED' and need not in agreed:
            raise ValueError(where + ' is CONTRADICTS_NEED and names no agreed NEED as needReqId: ' + repr(need))
        if verdict == 'RESTS_ON_SUPERSEDED' and need not in _superseded_needs(subjects[subject]):
            raise ValueError(where + ' is RESTS_ON_SUPERSEDED and names as needReqId ' + repr(need)
                             + ', which is no NEED it cites at a revision no longer in force')
        if verdict not in ('CONTRADICTS_NEED', 'RESTS_ON_SUPERSEDED') and need is not None:
            raise ValueError(where + ' is ' + verdict + ' and names a needReqId: only CONTRADICTS_NEED and'
                             ' RESTS_ON_SUPERSEDED do')
        if verdict == 'UNNEEDED' and not held:
            raise ValueError(where + ' is UNNEEDED, which is a held requirement\'s verdict only: an owned requirement no'
                             ' NEED states is OVER_REACH')
        if verdict == 'OVER_REACH' and held:
            raise ValueError(where + ' is OVER_REACH, which is an owned requirement\'s verdict only: a held requirement no'
                             ' NEED needs is UNNEEDED')
        item = {'subject': subject, 'verdict': verdict}
        if reason:
            item['text'] = reason
        if verdict == 'JUSTIFIED':
            item['needReqIds'] = ids
        if need is not None:
            item['needReqId'] = need
        by_subject[subject] = item
    missing = [s for s in chunk if s not in by_subject]
    if missing:
        raise ValueError('CC gave no verdict on ' + ', '.join(missing) + ': every requirement of the chunk gets one')
    return {'verdicts': [by_subject[s] for s in chunk]}


def run_prompt(task, function_code):
    context = context_of(io.read_role(task, 'backtrace-context'))
    chunk = chunk_of(io.read_role(task, 'subjects'), context)
    prompt = compose(context, chunk)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(function_code + ': ' + str(len(chunk)) + ' subject(s) of ' + str(len(context['subjects'])) + ', '
          + str(len(context['needs'])) + ' agreed NEED(s), ' + str(len(prompt)) + ' chars')


def run_check(task, function_code):
    context = context_of(io.read_role(task, 'backtrace-context'))
    chunk = chunk_of(io.read_role(task, 'subjects'), context)
    answer = verdicts_of(io.read_role(task, 'cc-result'), context, chunk)
    io.write_text(io.output_role(task, 'findings'), json.dumps(answer, ensure_ascii=False))
    print(function_code + ': ' + str(len(answer['verdicts'])) + ' verdict(s): '
          + ', '.join(v['verdict'] + '/' + v['subject'] + ('/' + v['needReqId'] if 'needReqId' in v else '')
                      for v in answer['verdicts']))
