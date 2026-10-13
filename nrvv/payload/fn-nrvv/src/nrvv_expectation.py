# The expectation analysis (plan 047, Phase 6): the prompt that asks CC to split a stakeholder's expectation - the text
# as written - into atomic clauses, each a proposed NEED, and the check of CC's answer.
#
# Offsets. A clause is a span [from, to) of the expectation text in UTF-16 units (what a Java String index counts). A
# model cannot count characters reliably, so the prompt lists the text as numbered PIECES with their offsets already
# computed, and CC copies them: a clause covering several consecutive pieces takes the first piece's from and the last
# piece's to.
#
# The answer is ONE JSON object {"clauses": [{"from", "to", "kind", "title", "statement", "mapping"?, "needReqId"?}]}:
#   from, to    the clause's span, inside the text; spans never overlap
#   kind        one of KINDS
#   title       a few words naming the need
#   statement   the clause restated as one need in the stakeholder's voice
#   mapping     only for an expectation with a parent: UNCHANGED | AMENDS | NEW
#   needReqId   UNCHANGED, AMENDS: the agreed NEED the clause maps to; NEW: null
# An agreed NEED of the parent that no clause names is retired - NRVV writes that proposal, not CC. The Dispatcher's
# mhdg-nrvv.store-expectation-analysis checks the same rules again before it writes.
#
# Pure: no I/O.

import json
import re

import nrvv_assessment as na
import nrvv_cc_answer as ca

KINDS = ('OBLIGATION', 'COST_OBJECTIVE', 'ENVIRONMENT_FACT', 'SCOPE_LIMITER')
MAPPINGS = ('UNCHANGED', 'AMENDS', 'NEW')
MAPPED = ('UNCHANGED', 'AMENDS')
FIELDS = ('from', 'to', 'kind', 'title', 'statement', 'mapping', 'needReqId')
# NRVV_PROPOSED_NEED.TITLE is VARCHAR(250)
TITLE_MAX_CHARS = 250

# a piece: from its first non-blank character up to and including a terminator followed by blank or the line's end,
# or - with no such terminator - to the line's last non-blank character
PIECE = re.compile(r'\S(?:.*?[.!?;,](?=\s|$)|(?:.*\S)?)')


def expectation_of(raw):
    """mhdg-nrvv.read-expectation's output, or a ValueError:
    {"expectationId", "parentId", "stakeholder", "text", "agreedNeeds": [{"needReqId", "title", "statement", "kind"}]}."""
    try:
        data = json.loads(raw or '')
    except ValueError:
        raise ValueError('the expectation is not JSON: ' + na.excerpt(raw)) from None
    if not isinstance(data, dict) or not isinstance(data.get('text'), str) or not data['text'].strip():
        raise ValueError('the expectation has no text: ' + na.excerpt(raw))
    needs = data.get('agreedNeeds')
    if needs is None:
        needs = []
    if not isinstance(needs, list) or any(not isinstance(n, dict) or not n.get('needReqId') for n in needs):
        raise ValueError('the agreed NEEDs of the expectation are not a list of NEEDs with a needReqId: ' + na.excerpt(raw))
    data['agreedNeeds'] = needs
    return data


def has_parent(expectation):
    return expectation.get('parentId') is not None


def utf16_len(s):
    return len(s.encode('utf-16-le')) // 2


def pieces(text):
    """The pieces of `text`, in order: [(from, to, piece)] with [from, to) in UTF-16 units."""
    out = []
    line_start = 0
    for line in text.split('\n'):
        for m in PIECE.finditer(line):
            start = line_start + m.start()
            end = line_start + m.end()
            out.append((utf16_len(text[:start]), utf16_len(text[:end]), m.group(0)))
        line_start += len(line) + 1
    return out


# The LAST part of the prompt: how the answer is stored. CC reads it after the text, so it acts on it.
ANSWER = [
    '',
    'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object, and nothing else:',
]
ANSWER_SHAPE = ('{"clauses": [{"from": <first piece\'s from>, "to": <last piece\'s to>, "kind": "<kind>", '
                '"title": "<title>", "statement": "<statement>"}]}')
ANSWER_SHAPE_PARENT = ('{"clauses": [{"from": <first piece\'s from>, "to": <last piece\'s to>, "kind": "<kind>", '
                       '"title": "<title>", "statement": "<statement>", "mapping": "<UNCHANGED|AMENDS|NEW>", '
                       '"needReqId": "<agreed NEED reqId, or null for NEW>"}]}')
ANSWER_TAIL = 'Print nothing - neither the clauses nor any explanation: only what the tool stores reaches the pipeline.'


def compose(expectation):
    """The expectation-analysis prompt over `expectation` (expectation_of's shape)."""
    stakeholder = str(expectation.get('stakeholder') or 'the stakeholder').strip()
    parent = has_parent(expectation)
    lines = [
        'You split a stakeholder\'s expectation - their words as written - into its clauses: atomic statements, each',
        'stating ONE need. You only split and restate; you never decide what an unclear word means.',
        '',
        'The expectation is listed below as numbered pieces, each with its offsets [from, to) in the text. A clause',
        'covers one piece or several consecutive pieces: its "from" is the first piece\'s from and its "to" is the last',
        'piece\'s to - copy both from the list, never count characters. Two clauses never share a piece. A piece that',
        'states no need (a heading, a greeting) belongs to no clause. Every need the text states belongs to a clause.',
        '',
        'For each clause:',
        '- kind, one of:',
        '  OBLIGATION - something the stakeholder needs to hold;',
        '  COST_OBJECTIVE - a cost the stakeholder wants kept low: an objective to weigh, never a fixed bound;',
        '  ENVIRONMENT_FACT - how the world around the system behaves, not something the system does;',
        '  SCOPE_LIMITER - what matters or does not matter, what is out of scope.',
        '- title: a few words naming the need.',
        '- statement: the clause restated as one need in the stakeholder\'s voice ("The ' + stakeholder + ' needs ...").',
        '  Add nothing the clause does not say: no number, duration, rate or limit the text does not state, no',
        '  mechanism or design, and no decision on what an ambiguous word means - keep the ambiguous word.',
    ]
    if parent:
        lines += [
            '',
            'This expectation is a new version of one whose clauses are already agreed as the NEEDs listed below.',
            'For each clause also give:',
            '- mapping: UNCHANGED - an agreed NEED already says what the clause says; AMENDS - the clause changes what',
            '  an agreed NEED says; NEW - no agreed NEED covers the clause.',
            '- needReqId: for UNCHANGED and AMENDS the reqId of that agreed NEED, exactly as listed; for NEW null.',
            'Each agreed NEED is named by at most one clause. An agreed NEED that no clause names is retired, so name',
            'every agreed NEED whose need the text still states.',
            '',
            'The agreed NEEDs:',
        ]
        for n in expectation['agreedNeeds']:
            kind = n.get('kind')
            lines.append('NEED ' + str(n.get('needReqId')) + (' (' + str(kind) + ')' if kind else '') + ': '
                         + str(n.get('title') or '').strip())
            lines.append('  ' + ' '.join(str(n.get('statement') or '').split()))
        if not expectation['agreedNeeds']:
            lines.append('(none)')
    lines += ['', 'Stakeholder: ' + stakeholder, '', 'The expectation, piece by piece:']
    for frm, to, piece in pieces(expectation['text']):
        lines.append('[' + str(frm) + ',' + str(to) + ') ' + piece)
    return '\n'.join(lines + ANSWER + [ANSWER_SHAPE_PARENT if parent else ANSWER_SHAPE, ANSWER_TAIL])


def _int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def clauses_of(cc_result, expectation):
    """CC's clauses as the canonical answer {"clauses": [...]} ordered by `from`, or a ValueError naming the first
    violation."""
    text = (cc_result or '').strip()
    fenced = na.FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    data = ca.loads(text)
    if not isinstance(data, dict) or set(data.keys()) != {'clauses'} or not isinstance(data['clauses'], list):
        raise ValueError('CC answered no {"clauses": [...]} object: ' + na.excerpt(text))
    if not data['clauses']:
        raise ValueError('CC answered no clause: an expectation states at least one need')
    parent = has_parent(expectation)
    agreed = {str(n['needReqId']) for n in expectation['agreedNeeds']}
    length = utf16_len(expectation['text'])
    named = set()
    out = []
    for i, c in enumerate(data['clauses']):
        where = 'clause #' + str(i)
        if not isinstance(c, dict):
            raise ValueError(where + ' is not an object')
        extra = [k for k in c.keys() if k not in FIELDS]
        if extra:
            raise ValueError(where + ' has an unknown field ' + repr(extra[0]))
        frm, to = c.get('from'), c.get('to')
        if not _int(frm) or not _int(to):
            raise ValueError(where + ' has no integer from / to')
        if frm < 0 or to > length or to <= frm:
            raise ValueError(where + ' span [' + str(frm) + ',' + str(to) + ') is not inside the text of '
                             + str(length) + ' units, or is empty')
        kind = c.get('kind')
        if kind not in KINDS:
            raise ValueError(where + ' has an unknown kind ' + repr(kind))
        title = c.get('title')
        statement = c.get('statement')
        if not isinstance(title, str) or not title.strip():
            raise ValueError(where + ' has no title')
        if '\n' in title.strip() or '\r' in title.strip():
            raise ValueError(where + ' has a title of more than one line')
        if len(title.strip()) > TITLE_MAX_CHARS:
            raise ValueError(where + ' has a title over ' + str(TITLE_MAX_CHARS) + ' characters')
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError(where + ' has an empty statement')
        mapping = c.get('mapping')
        need = c.get('needReqId')
        need = None if need is None else str(need).strip() or None
        item = {'from': frm, 'to': to, 'kind': kind, 'title': title.strip(), 'statement': statement.strip()}
        if not parent:
            if mapping is not None or need is not None:
                raise ValueError(where + ' has a mapping, but the expectation has no parent to map to')
        else:
            if mapping not in MAPPINGS:
                raise ValueError(where + ' has an unknown mapping ' + repr(mapping))
            if mapping in MAPPED:
                if need not in agreed:
                    raise ValueError(where + ' is ' + mapping + ' and names no agreed NEED: ' + repr(need))
                if need in named:
                    raise ValueError(where + ' names NEED ' + need + ' a second time')
                named.add(need)
            elif need is not None:
                raise ValueError(where + ' is NEW and names NEED ' + need)
            item['mapping'] = mapping
            item['needReqId'] = need
        out.append(item)
    out.sort(key=lambda x: x['from'])
    for a, b in zip(out, out[1:]):
        if b['from'] < a['to']:
            raise ValueError('clauses [' + str(a['from']) + ',' + str(a['to']) + ') and [' + str(b['from']) + ','
                             + str(b['to']) + ') overlap')
    return {'clauses': out}
