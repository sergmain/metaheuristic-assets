# The needs CV (plan 045, Phase 9): the prompt that asks CC to judge a project's agreed NEEDs as a set - within the set
# and across the trace to the requirements that answer them - and the check of CC's answer. CC produces findings only:
# a person disposes of each one in NRVV's UI (DISMISSED, CONFIRMED, PROPOSAL_CREATED).
#
# The answer is ONE JSON object {"findings": [{"kind", "subject", "counterpart"?, "text"}]}:
#   kind         one of KINDS
#   subject      the reqId of the agreed NEED the finding is about - always one of the NEEDs the run was given
#   counterpart  CONTRADICTION, REDUNDANCY: another agreed NEED (required); INCOHERENT_TRACE: a requirement the subject
#                traces to (required); any other kind: either of those, or nothing
#   text         what the finding is, in one or two sentences
# ASSUMPTION findings are not CC's: NRVV writes them from the `assumed: ...` items of the traced requirements'
# Rationale. The Dispatcher's mhdg-nrvv.store-findings checks the same rules again before it writes
# (NrvvFindingUtils.parseNeedsCvFindings): a bad answer fails HERE, at the check Task, where resetting the CC Task
# repairs it.
#
# Pure: no I/O.

import json

import nrvv_assessment as na

KINDS = ('CONTRADICTION', 'REDUNDANCY', 'GAP', 'VAGUE_TERM', 'SOLUTION_STATEMENT', 'SYSTEM_VOICE', 'NOT_SINGULAR',
         'INCOHERENT_TRACE')
PAIR_KINDS = ('CONTRADICTION', 'REDUNDANCY')
FIELDS = ('kind', 'subject', 'counterpart', 'text')


def trace_of(raw):
    """The agreed NEEDs with their trace (mhdg-nrvv.read-trace: NrvvData.TracedNeed list), or a ValueError."""
    try:
        data = json.loads(raw or '')
    except ValueError:
        raise ValueError('the trace is not JSON: ' + na.excerpt(raw)) from None
    if not isinstance(data, list) or any(not isinstance(n, dict) or not n.get('needReqId')
                                         or not isinstance(n.get('requirements'), list) for n in data):
        raise ValueError('the trace is not a list of NEEDs with a needReqId and requirements: ' + na.excerpt(raw))
    return data


def traced_by_need(trace):
    """needReqId -> the requirements it traces to: lineage roots and their live members."""
    out = {}
    for n in trace:
        ids = set()
        for r in n['requirements']:
            ids.add(str(r.get('reqId')))
            if r.get('liveReqId'):
                ids.add(str(r.get('liveReqId')))
        out[str(n['needReqId'])] = ids
    return out


def compose(trace):
    """The needs-CV prompt over `trace`."""
    lines = [
        'You review the stakeholder NEEDs a project has agreed, as a set, and the requirements that answer them.',
        '',
        'A NEED states what a stakeholder needs, in the stakeholder\'s voice. You do not decide anything: a person',
        'settles every finding you report. You only report findings, each about something the person must see.',
        '',
        'Finding kinds, each about ONE agreed NEED, its subject:',
        '- CONTRADICTION: the subject and another agreed NEED cannot both hold. Name that NEED as counterpart.',
        '- REDUNDANCY: another agreed NEED already says what the subject says, wholly or in part. Name it as',
        '  counterpart.',
        '- GAP: the NEEDs evidently rely on something no agreed NEED states. The subject is the NEED that relies on it.',
        '- VAGUE_TERM: the subject uses a term that cannot be checked as stated (quickly, user-friendly, as needed).',
        '- SOLUTION_STATEMENT: the subject prescribes a solution (a technology, a design, a mechanism) rather than',
        '  stating a need.',
        '- SYSTEM_VOICE: the subject is worded as what a system shall do, not as what a stakeholder needs.',
        '- NOT_SINGULAR: the subject states more than one need.',
        '- INCOHERENT_TRACE: a requirement the subject traces to no longer serves the subject as it now reads - its',
        '  revision changed and the requirement still answers the old text, or never answered it. Name that',
        '  requirement (its reqId as listed under the NEED) as counterpart.',
        '',
        'Rules:',
        '- Report only what holds. No finding at all is a valid answer.',
        '- A subject is the reqId of one agreed NEED listed below; a counterpart is another listed NEED or, for',
        '  INCOHERENT_TRACE, a requirement listed under the subject - exactly as written there.',
        '- Each finding\'s text says what is wrong in one or two sentences, quoting the words concerned.',
        '- Do not report the "assumed: ..." items in the requirements\' Rationale: they are recorded separately.',
        '- Never recommend an outcome and never rewrite a NEED or a requirement.',
        '',
        'Store your answer with the result tool as exactly this JSON object, and nothing else:',
        '{"findings": [{"kind": "<kind>", "subject": "<NEED reqId>", "counterpart": "<reqId or null>", '
        '"text": "<what is wrong>"}]}',
        '',
    ]
    if not trace:
        lines.append('The project has no agreed NEED.')
        return '\n'.join(lines)
    lines.append('The agreed NEEDs, each with the requirements it traces to:')
    for n in trace:
        lines.append('')
        lines.append('NEED ' + str(n.get('needReqId')) + ' (revision ' + str(n.get('revision')) + '): '
                     + str(n.get('title') or '').strip())
        lines.append(str(n.get('statement') or '').strip())
        if not n['requirements']:
            lines.append('  It traces to no requirement.')
        for r in n['requirements']:
            live = r.get('liveReqId')
            if not live:
                lines.append('  Traces to ' + str(r.get('reqId')) + ', which is obsolete at this snapshot.')
                continue
            name = str(r.get('reqId')) if live == r.get('reqId') else str(r.get('reqId')) + ' (now ' + str(live) + ')'
            lines.append('  Traces to requirement ' + name + ':')
            for text_line in str(r.get('text') or '').strip().splitlines():
                lines.append('    ' + text_line)
    return '\n'.join(lines)


def findings_of(cc_result, trace):
    """CC's findings as the canonical answer {"findings": [...]}, or a ValueError naming the first violation."""
    text = (cc_result or '').strip()
    fenced = na.FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError('CC answered something that is not JSON: ' + na.excerpt(text)) from None
    if not isinstance(data, dict) or set(data.keys()) != {'findings'} or not isinstance(data['findings'], list):
        raise ValueError('CC answered no {"findings": [...]} object: ' + na.excerpt(text))
    traced = traced_by_need(trace)
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
        subject = str(f.get('subject') or '').strip()
        if subject not in traced:
            raise ValueError('finding #' + str(i) + ' names subject ' + repr(subject) + ', which is not one of the agreed NEEDs')
        counterpart = f.get('counterpart')
        counterpart = None if counterpart is None else str(counterpart).strip() or None
        other_need = counterpart is not None and counterpart != subject and counterpart in traced
        traced_req = counterpart is not None and counterpart in traced[subject]
        if kind in PAIR_KINDS and not other_need:
            raise ValueError('finding #' + str(i) + ' is a ' + kind + ' and names no other agreed NEED as counterpart')
        if kind == 'INCOHERENT_TRACE' and not traced_req:
            raise ValueError('finding #' + str(i) + ' is an INCOHERENT_TRACE and names no requirement '
                             + subject + ' traces to')
        if counterpart is not None and not other_need and not traced_req:
            raise ValueError('finding #' + str(i) + ' names counterpart ' + repr(counterpart)
                             + ', which is neither another agreed NEED nor a requirement ' + subject + ' traces to')
        item = {'kind': kind, 'subject': subject, 'text': finding_text.strip()}
        if counterpart is not None:
            item['counterpart'] = counterpart
        out.append(item)
    return {'findings': out}
