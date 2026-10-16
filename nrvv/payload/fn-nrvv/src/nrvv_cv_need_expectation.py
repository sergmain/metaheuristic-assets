# NEED check EXPECTATION (plan 048, Phase 5, decision 14): validation of the NEEDs against their expectation - does each
# agreed NEED say what its clause of the expectation says? The subjects are the agreed NEEDs whose text names an
# expectation span (their `clause`, the span's text, given by mhdg-nrvv.read-agreed-needs); one CC session per chunk of at
# most 40 of them answers, per subject, exactly one verdict:
#   FAITHFUL                 the NEED states what its clause states                                   - no finding
#   OVER_STATES              the NEED states something its clause does not; text: those words          - hard
#   CONTRADICTS_EXPECTATION  the NEED and its clause cannot both hold; text: the situation, both words - hard
#   UNDER_STATES             the NEED leaves out something its clause states; text: the clause's words - soft
# A NEED with no expectation span is not a subject: there is nothing to hold it against.
#
# The agreed NEEDs are mhdg-nrvv.read-agreed-needs's output: [{"reqId", "revision", "title", "statement", "parentReqId",
# "kind", "clause"}], `clause` null for a NEED without a span. The chunk is one reqId per line (mh.batch-line-splitter over
# the reader's output `subjects` - the NEEDs with a clause; nullified when there is none, so no chunk and no CC session).
#
# The canonical answer {"verdicts": [{"subject", "verdict", "text"}]} has exactly one entry per subject of the chunk, in
# chunk order. Every verdict but FAITHFUL gives its text - it is the finding stored; a FAITHFUL one stores nothing, so its
# text is optional (kept when given). The Dispatcher's mhdg-nrvv.store-findings checks the same rules again
# (NrvvFindingUtils.parseExpectation) and stores one finding per verdict other than FAITHFUL.
#
# Pure but for run_prompt() / run_check().

import json

import mh_task_io as io
import nrvv_assessment as na
import nrvv_cc_answer as ca
import nrvv_cv_need as cv

VERDICTS = ('FAITHFUL', 'OVER_STATES', 'CONTRADICTS_EXPECTATION', 'UNDER_STATES')
FIELDS = ('subject', 'verdict', 'text')
CHUNK_SIZE = 40

ANSWER_SHAPE = ('{"verdicts": [{"subject": "<NEED reqId>", '
                '"verdict": "<FAITHFUL|OVER_STATES|CONTRADICTS_EXPECTATION|UNDER_STATES>", "text": "<why>"}]}')


def clause_of(need):
    """The NEED's clause of its expectation, stripped, or None when it has none."""
    clause = need.get('clause')
    if not isinstance(clause, str) or not clause.strip():
        return None
    return clause.strip()


def subjects_of(needs):
    """The reqIds of the agreed NEEDs that have a clause - the subjects, in the order given."""
    return [str(n['reqId']) for n in needs if clause_of(n) is not None]


def chunk_of(raw, needs):
    """The subjects of one chunk - one reqId per line, each an agreed NEED with a clause - or a ValueError."""
    known = set(subjects_of(needs))
    ids = [line.strip() for line in (raw or '').splitlines() if line.strip()]
    if not ids:
        raise ValueError('the chunk names no subject')
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ValueError('the chunk names ' + repr(unknown[0]) + ', which is not an agreed NEED with a clause of an'
                         ' expectation')
    if len(set(ids)) != len(ids):
        raise ValueError('the chunk names a subject twice')
    return ids


def compose(needs, chunk):
    """The expectation-validation prompt for the subjects `chunk` of `needs`. The answer instruction is the LAST part."""
    by_id = {str(n['reqId']): n for n in needs}
    lines = [
        'You validate the NEEDs a project\'s stakeholders have agreed against the expectation they were parsed from:',
        'does each NEED say what its clause of the expectation says - no more, no less, and nothing against it?',
        '',
        'An expectation is the stakeholder\'s own text. An analysis split it into clauses and wrote a NEED for each clause;',
        'a NEED restates its clause in the stakeholder\'s voice. Each NEED below is shown with its clause, quoted exactly',
        'from the expectation.',
        '',
        'For EACH NEED listed under "NEEDs to judge", give exactly one verdict:',
        '- FAITHFUL: the NEED states what its clause states. Different words, a clearer word, a split sentence or',
        '  naming what "it" refers to is faithful.',
        '- OVER_STATES: the NEED states something its clause does not state - a number, a duration, a rate, a limit, a',
        '  mechanism, a behaviour, a party or a certainty the clause never states. The text quotes the NEED\'s words',
        '  that go beyond the clause.',
        '- CONTRADICTS_EXPECTATION: in some situation the NEED and its clause cannot both hold - the NEED states the',
        '  opposite, or makes optional what the clause requires. The text gives the situation, quoting the words of',
        '  both.',
        '- UNDER_STATES: the NEED leaves out something its clause states - a condition, a qualifier, a party or a cost.',
        '  The text quotes the clause\'s words the NEED drops.',
        '',
        'Rules:',
        '- Judge each NEED against ITS OWN clause only - not against other NEEDs, other clauses or what a good system',
        '  would do. Whether the NEED is feasible, wise or well written is not asked.',
        '- When more than one verdict applies, give the first that applies in this order: CONTRADICTS_EXPECTATION,',
        '  OVER_STATES, UNDER_STATES.',
        '- A clause that states a cost states an objective to weigh; a NEED that turns it into a fixed bound states a',
        '  limit the clause does not - OVER_STATES.',
        # plan 048 Phase 14 (#69 GASV6B1): the analysis words every clause "The <stakeholder> needs ..." - an
        # ENVIRONMENT_FACT's NEED "needs to account for <the fact>" was judged an obligation and the gate declined
        '- Every NEED is written in the stakeholder\'s voice ("The <stakeholder> needs ..."): the analysis words every',
        '  clause that way, so "needs" alone adds nothing to a clause.',
        '- A clause that states how the world behaves (an ENVIRONMENT_FACT) obliges nothing. A NEED that says the',
        '  stakeholder needs that fact accounted for, taken into account or handled states its clause - FAITHFUL. It',
        '  states more than its clause - OVER_STATES - only when it names what the system shall do about the fact: a',
        '  behaviour, a mechanism, a bound or a guarantee the clause does not state.',
        '- One verdict per listed NEED, its reqId as subject, exactly as written. Never rewrite a NEED or a clause.',
        '',
    ]
    lines += cv.KIND_HINT + ['', 'NEEDs to judge:']
    for req_id in chunk:
        n = by_id[req_id]
        kind = n.get('kind')
        lines.append('')
        lines.append('NEED ' + req_id + (' (' + str(kind) + ')' if kind else '') + ': ' + str(n.get('title') or '').strip())
        for text_line in str(n.get('statement') or '').strip().splitlines():
            lines.append('    ' + text_line)
        lines.append('    Its clause of the expectation:')
        for text_line in clause_of(n).splitlines():
            lines.append('    > ' + text_line)
    return '\n'.join(lines + [
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object - one entry per NEED',
        'listed, in the order listed - and nothing else:',
        ANSWER_SHAPE,
        cv.ANSWER_TAIL.replace('the findings', 'the verdicts'),
    ])


def verdicts_of(cc_result, chunk):
    """CC's verdicts as the canonical answer {"verdicts": [...]} in chunk order, or a ValueError naming the first violation."""
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
        if not reason and verdict != 'FAITHFUL':
            raise ValueError(where + ' has no text')
        item = {'subject': subject, 'verdict': verdict}
        if reason:
            item['text'] = reason
        by_subject[subject] = item
    missing = [s for s in chunk if s not in by_subject]
    if missing:
        raise ValueError('CC gave no verdict on ' + ', '.join(missing) + ': every NEED of the chunk gets one')
    return {'verdicts': [by_subject[s] for s in chunk]}


def run_prompt(task, function_code):
    needs = cv.needs_of(io.read_role(task, 'agreed-needs'))
    chunk = chunk_of(io.read_role(task, 'subjects'), needs)
    prompt = compose(needs, chunk)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(function_code + ': ' + str(len(chunk)) + ' NEED(s) of ' + str(len(subjects_of(needs))) + ' with a clause, '
          + str(len(prompt)) + ' chars')


def run_check(task, function_code):
    needs = cv.needs_of(io.read_role(task, 'agreed-needs'))
    chunk = chunk_of(io.read_role(task, 'subjects'), needs)
    answer = verdicts_of(io.read_role(task, 'cc-result'), chunk)
    io.write_text(io.output_role(task, 'findings'), json.dumps(answer, ensure_ascii=False))
    print(function_code + ': ' + str(len(answer['verdicts'])) + ' verdict(s): '
          + ', '.join(v['verdict'] + '/' + v['subject'] for v in answer['verdicts']))
