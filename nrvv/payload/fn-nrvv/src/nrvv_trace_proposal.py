# Trace proposals (plan 045, Phase 17): the prompt that asks CC, per orphan of one chunk, how the requirement is
# justified - by a stakeholder NEED, by an imposed held requirement, or not at all - and the check of CC's answer. CC
# only proposes: a person confirms or dismisses every proposal in NRVV's UI.
#
# An orphan is a requirement the traceability rule does not reach: a top-level requirement with no TRACE edge from an
# ACTIVE NEED and no COMPLIANCE edge from an imposed held requirement, or a requirement whose DERIVATION path reaches no
# live top-level one. It is named by its lineage root.
#
# The answer is ONE JSON object {"findings": [{"kind", "subject", "counterpart"?, "text"}]} with EXACTLY one entry per
# orphan of the chunk:
#   kind         TRACE_PROPOSAL      - counterpart: the reqId of the ACTIVE NEED the requirement serves
#                COMPLIANCE_PROPOSAL - counterpart: the reqId of the imposed held requirement it answers
#                NOT_TO_PORT         - no counterpart: nothing justifies it, it is not carried over
#   subject      the orphan's reqId, as listed
#   text         why, in one or two sentences
# An orphan that is not top-level takes NOT_TO_PORT only: a link on it would not justify it.
# The Dispatcher's mhdg-nrvv.store-findings checks the same rules again before it writes
# (NrvvTraceUtils.parseTraceProposals): a bad answer fails HERE, at the check Task, where resetting the CC Task repairs it.
#
# Pure: no I/O.

import json

import nrvv_assessment as na

KINDS = ('TRACE_PROPOSAL', 'COMPLIANCE_PROPOSAL', 'NOT_TO_PORT')
FIELDS = ('kind', 'subject', 'counterpart', 'text')


def context_of(raw):
    """The trace context (mhdg-nrvv.read-drift: NrvvData.TraceContext), or a ValueError."""
    try:
        data = json.loads(raw or '')
    except ValueError:
        raise ValueError('the trace context is not JSON: ' + na.excerpt(raw)) from None
    if not isinstance(data, dict) or any(not isinstance(data.get(k), list) for k in ('needs', 'heldMembers', 'orphans')):
        raise ValueError('the trace context has no needs, heldMembers and orphans lists: ' + na.excerpt(raw))
    for k in ('needs', 'heldMembers', 'orphans'):
        if any(not isinstance(x, dict) or not x.get('reqId') for x in data[k]):
            raise ValueError('the trace context has an entry of ' + k + ' with no reqId')
    return data


def chunk_of(raw, context):
    """The orphans of one chunk - one reqId per line, each an orphan of the context - or a ValueError."""
    known = {str(o['reqId']) for o in context['orphans']}
    ids = [line.strip() for line in (raw or '').splitlines() if line.strip()]
    if not ids:
        raise ValueError('the chunk names no orphan')
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ValueError('the chunk names ' + repr(unknown[0]) + ', which is not an orphan of the trace context')
    if len(set(ids)) != len(ids):
        raise ValueError('the chunk names an orphan twice')
    return ids


def compose(context, chunk):
    """The trace-proposal prompt for the orphans `chunk` of `context`."""
    orphans = {str(o['reqId']): o for o in context['orphans']}
    lines = [
        'You review requirements that nothing justifies yet, and propose how each one is justified.',
        '',
        'A NEED states what a stakeholder needs. A requirement states what the system shall do. A requirement is',
        'justified when it serves an agreed NEED, or when it answers an imposed held requirement - a requirement this',
        'project must comply with (a standard, a prime contractor\'s allocation). You do not decide anything: a person',
        'confirms or dismisses every proposal you make.',
        '',
        'For EACH requirement listed under "Requirements to justify", propose exactly one of:',
        '- TRACE_PROPOSAL: the requirement serves an agreed NEED. Name that NEED\'s reqId as counterpart.',
        '- COMPLIANCE_PROPOSAL: the requirement answers an imposed held requirement. Name that held requirement\'s',
        '  reqId as counterpart.',
        '- NOT_TO_PORT: no agreed NEED and no imposed held requirement justifies it - it is baggage of the existing',
        '  build (a workaround, a debug aid, a legacy constraint) that should not be carried over. No counterpart.',
        '',
        'Rules:',
        '- Exactly one proposal per listed requirement, its reqId as subject, exactly as written.',
        '- A requirement marked "not top-level" takes NOT_TO_PORT only.',
        '- Propose a link only when the requirement really serves that NEED or answers that held requirement; when',
        '  none fits, propose NOT_TO_PORT and say what the requirement does that no NEED asks for.',
        '- Prefer a NEED marked "traces to nothing yet" when it fits as well as another.',
        '- Never invent a NEED or a held requirement, and never rewrite a requirement.',
        '- Each proposal\'s text says why, in one or two sentences, quoting the words concerned.',
        '',
        'Store your answer with the result tool as exactly this JSON object, and nothing else:',
        '{"findings": [{"kind": "<kind>", "subject": "<requirement reqId>", "counterpart": "<reqId or null>", '
        '"text": "<why>"}]}',
        '',
    ]
    if context['needs']:
        lines.append('The agreed NEEDs:')
        for n in context['needs']:
            lines.append('')
            lines.append('NEED ' + str(n['reqId']) + ' (revision ' + str(n.get('revision')) + ')'
                         + (', traces to nothing yet' if n.get('gap') else '') + ': ' + str(n.get('title') or '').strip())
            lines.append(str(n.get('statement') or '').strip())
    else:
        lines.append('The project has no agreed NEED.')
    lines.append('')
    if context['heldMembers']:
        lines.append('The imposed held requirements:')
        for h in context['heldMembers']:
            lines.append('')
            lines.append('Held requirement ' + str(h['reqId']) + ' (section ' + str(h.get('sectionReqId')) + '):')
            for text_line in str(h.get('text') or '').strip().splitlines():
                lines.append('    ' + text_line)
    else:
        lines.append('The project holds no imposed requirement.')
    lines.append('')
    lines.append('Requirements to justify:')
    for req_id in chunk:
        o = orphans[req_id]
        lines.append('')
        live = o.get('liveReqId')
        name = req_id if not live or live == req_id else req_id + ' (now ' + str(live) + ')'
        lines.append('Requirement ' + name + (', top-level' if o.get('topLevel') else ', not top-level - NOT_TO_PORT only') + ':')
        for text_line in str(o.get('text') or '').strip().splitlines():
            lines.append('    ' + text_line)
        rationale = str(o.get('rationale') or '').strip()
        if rationale:
            lines.append('    Rationale: ' + rationale.replace('\n', ' '))
    return '\n'.join(lines)


def findings_of(cc_result, context, chunk):
    """CC's proposals as the canonical answer {"findings": [...]} in chunk order, or a ValueError naming the first violation."""
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
    needs = {str(n['reqId']) for n in context['needs']}
    held = {str(h['reqId']) for h in context['heldMembers']}
    top_level = {str(o['reqId']): bool(o.get('topLevel')) for o in context['orphans']}
    wanted = set(chunk)
    by_subject = {}
    for i, f in enumerate(data['findings']):
        if not isinstance(f, dict):
            raise ValueError('proposal #' + str(i) + ' is not an object')
        extra = [k for k in f.keys() if k not in FIELDS]
        if extra:
            raise ValueError('proposal #' + str(i) + ' has an unknown field ' + repr(extra[0]))
        kind = f.get('kind')
        if kind not in KINDS:
            raise ValueError('proposal #' + str(i) + ' has an unknown kind ' + repr(kind))
        reason = f.get('text')
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('proposal #' + str(i) + ' has no text')
        subject = str(f.get('subject') or '').strip()
        if subject not in wanted:
            raise ValueError('proposal #' + str(i) + ' names subject ' + repr(subject) + ', which is not a requirement of this chunk')
        if subject in by_subject:
            raise ValueError('proposal #' + str(i) + ' names ' + subject + ' a second time')
        counterpart = f.get('counterpart')
        counterpart = None if counterpart is None else str(counterpart).strip() or None
        if kind == 'TRACE_PROPOSAL' and counterpart not in needs:
            raise ValueError('proposal #' + str(i) + ' is a TRACE_PROPOSAL and names no agreed NEED as counterpart: ' + repr(counterpart))
        if kind == 'COMPLIANCE_PROPOSAL' and counterpart not in held:
            raise ValueError('proposal #' + str(i) + ' is a COMPLIANCE_PROPOSAL and names no imposed held requirement as'
                             ' counterpart: ' + repr(counterpart))
        if kind == 'NOT_TO_PORT' and counterpart is not None:
            raise ValueError('proposal #' + str(i) + ' is a NOT_TO_PORT and names a counterpart: ' + repr(counterpart))
        if kind != 'NOT_TO_PORT' and not top_level.get(subject):
            raise ValueError('proposal #' + str(i) + ' is a ' + kind + ' for ' + subject
                             + ', which is not top-level - only NOT_TO_PORT applies')
        item = {'kind': kind, 'subject': subject, 'text': reason.strip()}
        if counterpart is not None:
            item['counterpart'] = counterpart
        by_subject[subject] = item
    missing = [s for s in chunk if s not in by_subject]
    if missing:
        raise ValueError('CC proposed nothing for ' + ', '.join(missing) + ': every requirement of the chunk gets one proposal')
    return {'findings': [by_subject[s] for s in chunk]}
