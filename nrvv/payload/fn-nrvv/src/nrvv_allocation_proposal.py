# Allocation proposals (plan 045, Phase 25): the prompt that asks CC, per unallocated top-level requirement, which
# architecture element must meet it - one element, or a split into per-element shares - and the check of CC's answer.
# CC only proposes: a person confirms or dismisses every proposal in NRVV's UI.
#
# The context is mhdg-nrvv.read-allocation-input's output (NrvvData.AllocationContext as JSON):
#   elements    [{"code", "name", "description"}]
#   topLevel    [{"reqId", "liveReqId", "title", "statement", "designItems": [reqId]}] - the requirements to allocate
#   items       [{"reqId", "liveReqId", "kind", "parents", "title", "statement", "rationale"}] - design, Interface,
#               Environment items
#   allocated   {lineage root: element code} - the allocations in force
#
# The answer is ONE JSON object {"findings": [...]} with EXACTLY one entry per requirement to allocate:
#   {"kind": "ALLOCATION_PROPOSAL", "subject": "<reqId>", "element": "<element code>", "text": "<why>"}
#   {"kind": "ALLOCATION_PROPOSAL", "subject": "<reqId>", "shares": [{"element": "<code>", "text": "<statement>"}, ...],
#    "text": "<why>"}
# exactly one of element and shares; a split has at least two shares, each for a different element, each text at most
# SHARE_MAX_BYTES UTF-8 bytes. A missing kind is read as ALLOCATION_PROPOSAL; a null element or null shares as absent.
# The Dispatcher's mhdg-nrvv.store-findings checks the same rules again (NrvvAllocationUtils.parseAllocationProposals):
# a bad answer fails HERE, at the check Task, where resetting the CC Task repairs it.
#
# Pure: no I/O.

import json

import nrvv_assessment as na

KIND = 'ALLOCATION_PROPOSAL'
FIELDS = ('kind', 'subject', 'element', 'shares', 'text')
SHARE_FIELDS = ('element', 'text')
SHARE_MAX_BYTES = 2000


def context_of(raw):
    """The allocation context (mhdg-nrvv.read-allocation-input: NrvvData.AllocationContext), or a ValueError."""
    try:
        data = json.loads(raw or '')
    except ValueError:
        raise ValueError('the allocation context is not JSON: ' + na.excerpt(raw)) from None
    if not isinstance(data, dict) or any(not isinstance(data.get(k), list) for k in ('elements', 'topLevel', 'items')):
        raise ValueError('the allocation context has no elements, topLevel and items lists: ' + na.excerpt(raw))
    if any(not isinstance(e, dict) or not e.get('code') for e in data['elements']):
        raise ValueError('the allocation context has an element with no code')
    for k in ('topLevel', 'items'):
        if any(not isinstance(x, dict) or not x.get('reqId') for x in data[k]):
            raise ValueError('the allocation context has an entry of ' + k + ' with no reqId')
    if not data['elements']:
        raise ValueError('the allocation context has no element')
    if not data['topLevel']:
        raise ValueError('the allocation context has no requirement to allocate')
    if not isinstance(data.get('allocated'), dict):
        data['allocated'] = {}
    return data


def compose(context):
    """The allocation-proposal prompt for every requirement to allocate of `context`."""
    items = {str(i['reqId']): i for i in context['items']}
    lines = [
        'You allocate the requirements of a system to the architecture elements that must meet them.',
        '',
        'The system is split into the elements listed below. Allocation assigns each requirement to the one element',
        'that must meet it. When no single element can meet a requirement alone, the requirement is split: one share',
        'per element that must take part, each share a requirement that its element alone can meet, so that together',
        'the shares meet the whole requirement. You do not decide anything: a person confirms or dismisses every',
        'proposal you make.',
        '',
        'For EACH requirement listed under "Requirements to allocate", propose exactly one of:',
        '- one element: the code of the element that must meet the requirement;',
        '- a split: at least two shares, each naming a different element\'s code and the share\'s text - a requirement',
        '  statement whose subject is the system ("The service shall ..."), worded so that this element alone can meet it.',
        '',
        'Rules:',
        '- Exactly one proposal per listed requirement, its reqId as subject, exactly as written.',
        '- Prefer one element; split only when the requirement really needs more than one element to be met.',
        '- Use only the element codes listed. Never invent an element, and never rewrite the requirement itself.',
        '- A share states only what its element must do, in at most ' + str(SHARE_MAX_BYTES) + ' bytes.',
        '- The design items listed under a requirement show how it is meant to be built: use them to tell which',
        '  element does what.',
        '- Each proposal\'s text says why, in one or two sentences.',
        '',
        'Store your answer with the result tool as exactly this JSON object, and nothing else:',
        '{"findings": [{"kind": "ALLOCATION_PROPOSAL", "subject": "<requirement reqId>", "element": "<element code>", '
        '"text": "<why>"}, {"kind": "ALLOCATION_PROPOSAL", "subject": "<requirement reqId>", "shares": '
        '[{"element": "<element code>", "text": "<share statement>"}, {"element": "<element code>", "text": "<share '
        'statement>"}], "text": "<why>"}]}',
        'Each proposal has either "element" or "shares", never both.',
        '',
        'The elements:',
    ]
    for e in context['elements']:
        description = str(e.get('description') or '').strip()
        lines.append('- ' + str(e['code']) + ': ' + str(e.get('name') or '').strip()
                     + (' - ' + description.replace('\n', ' ') if description else ''))
    lines.append('')
    if context['allocated']:
        lines.append('Requirements allocated already (for context, not to answer):')
        for root, code in context['allocated'].items():
            lines.append('- ' + str(root) + ' -> ' + str(code))
        lines.append('')
    if context['items']:
        lines.append('The design items:')
        for i in context['items']:
            lines.append('')
            lines.append('Design item ' + str(i['reqId']) + ' (' + str(i.get('kind') or 'design') + '): '
                         + str(i.get('title') or '').strip())
            for text_line in str(i.get('statement') or '').strip().splitlines():
                lines.append('    ' + text_line)
        lines.append('')
    lines.append('Requirements to allocate:')
    for t in context['topLevel']:
        req_id = str(t['reqId'])
        live = t.get('liveReqId')
        name = req_id if not live or live == req_id else req_id + ' (now ' + str(live) + ')'
        lines.append('')
        lines.append('Requirement ' + name + ': ' + str(t.get('title') or '').strip())
        for text_line in str(t.get('statement') or '').strip().splitlines():
            lines.append('    ' + text_line)
        design = [str(d) for d in (t.get('designItems') or []) if str(d) in items]
        if design:
            lines.append('    Design items: ' + ', '.join(design))
    return '\n'.join(lines)


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def findings_of(cc_result, context):
    """CC's proposals as the canonical answer {"findings": [...]} in context order, or a ValueError naming the first violation."""
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
    codes = {str(e['code']) for e in context['elements']}
    order = [str(t['reqId']) for t in context['topLevel']]
    wanted = set(order)
    by_subject = {}
    for i, f in enumerate(data['findings']):
        if not isinstance(f, dict):
            raise ValueError('proposal #' + str(i) + ' is not an object')
        extra = [k for k in f.keys() if k not in FIELDS]
        if extra:
            raise ValueError('proposal #' + str(i) + ' has an unknown field ' + repr(extra[0]))
        kind = f.get('kind', KIND)
        if kind != KIND:
            raise ValueError('proposal #' + str(i) + ' has an unknown kind ' + repr(kind))
        reason = f.get('text')
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('proposal #' + str(i) + ' has no text')
        subject = str(f.get('subject') or '').strip()
        if subject not in wanted:
            raise ValueError('proposal #' + str(i) + ' names subject ' + repr(subject) + ', which is not a requirement to allocate')
        if subject in by_subject:
            raise ValueError('proposal #' + str(i) + ' names ' + subject + ' a second time')
        element = None if _blank(f.get('element')) else f.get('element')
        shares = f.get('shares')
        if (element is None) == (shares is None):
            raise ValueError('proposal #' + str(i) + ' for ' + subject + ' names exactly one of an element and shares')
        item = {'kind': KIND, 'subject': subject}
        if element is not None:
            code = str(element).strip()
            if code not in codes:
                raise ValueError('proposal #' + str(i) + ' for ' + subject + ' names an unknown element ' + repr(code))
            item['element'] = code
        else:
            item['shares'] = _shares_of(i, subject, shares, codes)
        item['text'] = reason.strip()
        by_subject[subject] = item
    missing = [s for s in order if s not in by_subject]
    if missing:
        raise ValueError('CC proposed nothing for ' + ', '.join(missing) + ': every requirement to allocate gets one proposal')
    return {'findings': [by_subject[s] for s in order]}


def _shares_of(i, subject, shares, codes):
    if not isinstance(shares, list) or len(shares) < 2:
        raise ValueError('proposal #' + str(i) + ' for ' + subject + ' splits into fewer than two shares')
    out = []
    seen = set()
    for j, s in enumerate(shares):
        where = 'proposal #' + str(i) + ', share #' + str(j)
        if not isinstance(s, dict):
            raise ValueError(where + ' is not an object')
        extra = [k for k in s.keys() if k not in SHARE_FIELDS]
        if extra:
            raise ValueError(where + ' has an unknown field ' + repr(extra[0]))
        code = str(s.get('element') or '').strip()
        if code not in codes:
            raise ValueError(where + ' names an unknown element ' + repr(code))
        if code in seen:
            raise ValueError('proposal #' + str(i) + ' for ' + subject + ' gives element ' + repr(code) + ' two shares')
        seen.add(code)
        share_text = s.get('text')
        if not isinstance(share_text, str) or not share_text.strip():
            raise ValueError(where + ' has no text')
        if len(share_text.strip().encode('utf-8')) > SHARE_MAX_BYTES:
            raise ValueError(where + ' has a text over ' + str(SHARE_MAX_BYTES) + ' UTF-8 bytes')
        out.append({'element': code, 'text': share_text.strip()})
    return out
