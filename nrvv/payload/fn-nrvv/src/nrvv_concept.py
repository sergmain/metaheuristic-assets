# NRVV concept analysis (plan 050, decision 10) - a confirmed glossary of the load-bearing terms of an expectation and its
# agreed NEEDs. Phase 2 runs it as a probe (nrvv-concept-probe-synthetic-1.0, no RG write); Phase 11's flow reuses the
# prompts and checks.
#
#   terms      ONE session lists the load-bearing terms - words or phrases of the text on whose meaning a behaviour
#              depends - each with two to four candidate readings, every reading quoting the words of the text it rests
#              on. The check gives the readings their letters A - D in the order answered.
#   readings   CV_REPEAT independent sessions, each in a fresh context and blind to the others, pick per term the reading
#              the text supports, with a quote, or OPEN when the text supports more than one. Each session lists the
#              readings in an order rotated by its session number (the letters stay with their readings): an agreement
#              must not come from the position a reading is listed at.
#   agree      deterministic: a reading picked by CONFIRM_MIN sessions is CONFIRMED; OPEN picked by CONFIRM_MIN
#              sessions, or no agreement, is an OPEN term.
#
# Verbatim: a term and every quote must occur in the text - the expectation or a NEED's title or statement - compared
# with letter case, typographic quotes and runs of whitespace folded. The checks refuse an answer whose SHAPE is wrong
# (the Task fails); an item that fails the verbatim rule is not refused but set aside and recorded - a term is dropped
# (`dropped`), a session's pick becomes INVALID - so one copying slip does not cost the whole run, and the record shows it.
#
# The input of every step is the concept input {"expectation": "<text>", "needs": [{"reqId", "kind", "title",
# "statement"}]} (the probe gets it as a source-level Variable; Phase 10's mhdg-nrvv.read-concept-input writes the same
# shape).
#
# Pure but for the run_*() functions.

import json
import re

import mh_task_io as io
import nrvv_assessment as na
import nrvv_cc_answer as ca

CV_REPEAT = 3
CONFIRM_MIN = 2
MIN_READINGS = 2
MAX_READINGS = 4
MAX_TERMS = 24
LETTERS = ('A', 'B', 'C', 'D')
OPEN = 'OPEN'
INVALID = 'INVALID'
CONFIRMED = 'CONFIRMED'
OPEN_BY_AGREEMENT = 'OPEN_BY_AGREEMENT'
NO_AGREEMENT = 'NO_AGREEMENT'

TERMS_SHAPE = ('{"terms": [{"term": "<the words exactly as in the text>", "readings": [{"reading": "<what the term '
               'means>", "quote": "<words copied exactly from the text>"}]}]}')
READINGS_SHAPE = ('{"readings": [{"term": "<the term exactly as listed>", "pick": "<the letter of a reading, or OPEN>", '
                  '"quote": "<words copied exactly from the text>"}]}')
ANSWER_TAIL = 'Print nothing else - neither the answer nor any explanation: only what the tool stores reaches the pipeline.'

_QUOTES = str.maketrans({'\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"', '\u00a0': ' '})


# ==================== the input and the verbatim rule ====================

def input_of(raw):
    """The concept input, or a ValueError: an object with a non-blank expectation and a list of NEEDs, each with a
    reqId and a statement."""
    try:
        data = json.loads(raw or '')
    except ValueError:
        raise ValueError('the concept input is not JSON') from None
    if not isinstance(data, dict):
        raise ValueError('the concept input is not an object')
    expectation = data.get('expectation')
    if not isinstance(expectation, str) or not expectation.strip():
        raise ValueError('the concept input has no expectation text')
    needs = data.get('needs')
    if not isinstance(needs, list):
        raise ValueError('the concept input has no list of NEEDs')
    for i, n in enumerate(needs):
        if not isinstance(n, dict) or not str(n.get('reqId') or '').strip() or not str(n.get('statement') or '').strip():
            raise ValueError('NEED #' + str(i) + ' of the concept input has no reqId or no statement')
    return {'expectation': expectation, 'needs': needs}


def fold(text):
    """Text as the verbatim rule compares it: letter case, typographic quotes and runs of whitespace folded."""
    return ' '.join(str(text or '').translate(_QUOTES).lower().split())


def corpus(inp):
    """The text every term and quote must occur in: the expectation, then each NEED's title and statement."""
    parts = [inp['expectation']]
    for n in inp['needs']:
        parts.append(str(n.get('title') or ''))
        parts.append(str(n.get('statement') or ''))
    return fold('\n'.join(parts))


def verbatim(span, folded_corpus):
    """Whether `span` is a non-blank span of the text."""
    f = fold(span)
    return bool(f) and f in folded_corpus


def _text_block(inp):
    lines = ['The expectation (the stakeholder\'s own text):']
    lines += ['> ' + line for line in inp['expectation'].strip().splitlines()]
    lines += ['', 'The NEEDs agreed from it:']
    for n in inp['needs']:
        kind = n.get('kind')
        lines.append('')
        lines.append('NEED ' + str(n['reqId']) + (' (' + str(kind) + ')' if kind else '') + ': '
                     + str(n.get('title') or '').strip())
        lines += ['    ' + line for line in str(n.get('statement') or '').strip().splitlines()]
    return lines


def _decoded(cc_result, key):
    text = (cc_result or '').strip()
    fenced = na.FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    data = ca.loads(text)
    if not isinstance(data, dict) or set(data.keys()) != {key} or not isinstance(data[key], list):
        raise ValueError('CC answered no {"' + key + '": [...]} object: ' + na.excerpt(text))
    return data[key]


# ==================== terms ====================

def compose_terms(inp):
    """The terms prompt. The answer instruction is the LAST part."""
    lines = [
        'You analyse the words of a stakeholder\'s expectation and of the NEEDs agreed from it, before anything is designed.',
        '',
        'A load-bearing term is a word or a short phrase of the text on whose meaning a required behaviour depends: two',
        'careful readers could read it differently, and the systems they built would then behave differently. Such terms',
        'often name a state something reaches, an event that starts or ends a period, an ordering, an amount judged too',
        'much or too little, or the condition under which something counts as done. (In an unrelated text - a library\'s',
        'loan rules - "returned" could be such a term: is a book returned when it is dropped in the box, or when the desk',
        'checks it in?)',
        '',
        'List the load-bearing terms of the text below. For each term give two to ' + str(MAX_READINGS) + ' candidate',
        'readings - the different meanings a careful reader could give it in THIS text - and for every reading quote the',
        'words of the text that make that reading possible.',
        '',
        'Rules:',
        '- A term is copied exactly as it appears in the text (letter case aside). Words that do not appear in the text',
        '  are not a term of this text.',
        '- A reading says what the term means, in one sentence a tester could check. It adds no number, mechanism or',
        '  party the text does not name.',
        '- Each reading\'s quote is a span copied exactly from the text - the expectation or a NEED. Two readings of one',
        '  term may quote the same span.',
        '- List only terms with at least two genuinely different readings. A term whose meaning the text fixes is not',
        '  listed.',
        '- At most ' + str(MAX_TERMS) + ' terms, the most load-bearing first.',
        '- Do not choose between the readings: another step does that.',
        '',
    ]
    lines += _text_block(inp)
    return '\n'.join(lines + [
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object and nothing else:',
        TERMS_SHAPE,
        ANSWER_TAIL,
    ])


def terms_of(cc_result, inp):
    """CC's terms in canonical form {"terms": [{"term", "readings": [{"id", "reading", "quote"}]}], "dropped": [...]}, or
    a ValueError for a wrong shape. A term or a reading failing the verbatim rule is set aside (a term with fewer than
    two readings left is dropped); `dropped` names each, with why."""
    items = _decoded(cc_result, 'terms')
    folded = corpus(inp)
    terms, dropped, seen = [], [], set()
    for i, t in enumerate(items):
        where = 'term #' + str(i)
        if not isinstance(t, dict):
            raise ValueError(where + ' is not an object')
        extra = [k for k in t.keys() if k not in ('term', 'readings')]
        if extra:
            raise ValueError(where + ' has an unknown field ' + repr(extra[0]))
        term = t.get('term')
        readings = t.get('readings')
        if not isinstance(term, str) or not term.strip():
            raise ValueError(where + ' has no term')
        if not isinstance(readings, list):
            raise ValueError(where + ' (' + term + ') has no list of readings')
        term = term.strip()
        if fold(term) in seen:
            dropped.append({'term': term, 'why': 'listed twice'})
            continue
        if not verbatim(term, folded):
            dropped.append({'term': term, 'why': 'the term does not occur in the text'})
            continue
        kept = []
        for j, r in enumerate(readings):
            rw = where + ' (' + term + ') reading #' + str(j)
            if not isinstance(r, dict) or set(r.keys()) - {'reading', 'quote'}:
                raise ValueError(rw + ' is not an object of reading and quote')
            reading, quote = r.get('reading'), r.get('quote')
            if not isinstance(reading, str) or not reading.strip() or not isinstance(quote, str):
                raise ValueError(rw + ' has no reading or a quote that is not a string')
            if not verbatim(quote, folded):
                dropped.append({'term': term, 'why': 'reading #' + str(j) + ': its quote does not occur in the text'})
                continue
            if any(fold(k['reading']) == fold(reading) for k in kept):
                continue
            kept.append({'reading': reading.strip(), 'quote': quote.strip()})
        if len(kept) < MIN_READINGS:
            dropped.append({'term': term, 'why': 'fewer than ' + str(MIN_READINGS) + ' readings'})
            continue
        if len(terms) >= MAX_TERMS:
            dropped.append({'term': term, 'why': 'more than ' + str(MAX_TERMS) + ' terms'})
            continue
        seen.add(fold(term))
        kept = kept[:MAX_READINGS]
        for k, letter in zip(kept, LETTERS):
            k['id'] = letter
        terms.append({'term': term, 'readings': [{'id': k['id'], 'reading': k['reading'], 'quote': k['quote']}
                                                 for k in kept]})
    if not terms:
        raise ValueError('CC listed no usable term' + (': ' + json.dumps(dropped, ensure_ascii=False) if dropped else ''))
    return {'terms': terms, 'dropped': dropped}


def terms_doc(raw):
    """The canonical terms a check wrote, or a ValueError."""
    data = json.loads(raw or '')
    if not isinstance(data, dict) or not isinstance(data.get('terms'), list) or not data['terms']:
        raise ValueError('the terms are not a canonical {"terms": [...]} object')
    return data


def sessions_text(repeat=CV_REPEAT):
    """The splitter's input: one session number per line, 1-based."""
    return '\n'.join(str(i) for i in range(1, repeat + 1))


# ==================== readings ====================

def session_of(raw):
    """The session number of a readings branch - its chunk, one positive integer - or a ValueError."""
    lines = [line.strip() for line in (raw or '').splitlines() if line.strip()]
    if len(lines) != 1 or not lines[0].isdigit() or int(lines[0]) < 1:
        raise ValueError('the session chunk is not one session number: ' + repr(raw))
    return int(lines[0])


def rotated(readings, session):
    """The readings in the order session `session` lists them: rotated left by session - 1."""
    if not readings:
        return []
    k = (session - 1) % len(readings)
    return readings[k:] + readings[:k]


def compose_readings(inp, terms, session):
    """The readings prompt of one session. The answer instruction is the LAST part."""
    lines = [
        'You decide what the load-bearing terms of a stakeholder\'s text mean, from the text alone.',
        '',
        'Below are the expectation, the NEEDs agreed from it, and a list of terms, each with candidate readings marked by',
        'a letter. For EACH term pick the reading the text supports and quote the words of the text that support it.',
        'When the text supports more than one reading - nothing in it decides the choice - answer OPEN.',
        '',
        'Rules:',
        '- Decide from the text only. What a well-designed system would do, what is usual in the domain, or what is',
        '  cheaper to build is not evidence.',
        '- Pick a reading only when the words you quote support it better than every other reading of that term;',
        '  otherwise answer OPEN.',
        '- The quote is a span copied exactly from the text - the expectation or a NEED. An OPEN answer may quote the',
        '  words that leave the choice open.',
        '- The letters belong to the readings; the order the readings are listed in means nothing.',
        '- One answer per listed term, its term exactly as listed, in the order listed.',
        '',
    ]
    lines += _text_block(inp)
    lines += ['', 'The terms:']
    for t in terms['terms']:
        lines.append('')
        lines.append('Term "' + t['term'] + '":')
        for r in rotated(t['readings'], session):
            lines.append('  ' + r['id'] + ': ' + r['reading'] + '   (rests on: "' + r['quote'] + '")')
    return '\n'.join(lines + [
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object - one entry per term,',
        'in the order listed - and nothing else:',
        READINGS_SHAPE,
        ANSWER_TAIL,
    ])


def readings_of(cc_result, terms, inp, session):
    """One session's picks in canonical form {"session", "readings": [{"term", "pick", "quote"?, "why"?}]}, one per term
    in term order, or a ValueError for a wrong shape (a term missing or named twice, an unknown field). A pick that is
    no letter of its term, or a letter whose quote does not occur in the text, is recorded as INVALID with why."""
    items = _decoded(cc_result, 'readings')
    folded = corpus(inp)
    by_term = {fold(t['term']): t for t in terms['terms']}
    picks = {}
    for i, r in enumerate(items):
        where = 'reading #' + str(i)
        if not isinstance(r, dict):
            raise ValueError(where + ' is not an object')
        extra = [k for k in r.keys() if k not in ('term', 'pick', 'quote')]
        if extra:
            raise ValueError(where + ' has an unknown field ' + repr(extra[0]))
        key = fold(r.get('term'))
        if key not in by_term:
            raise ValueError(where + ' names the term ' + repr(r.get('term')) + ', which is not listed')
        if key in picks:
            raise ValueError(where + ' names ' + repr(r.get('term')) + ' a second time')
        term = by_term[key]
        pick = str(r.get('pick') or '').strip().upper()
        quote = r.get('quote')
        quote = quote.strip() if isinstance(quote, str) else ''
        entry = {'term': term['term'], 'pick': pick}
        if quote:
            entry['quote'] = quote
        if pick != OPEN and pick not in [x['id'] for x in term['readings']]:
            entry['pick'], entry['why'] = INVALID, 'answered ' + repr(r.get('pick')) + ', no letter of this term'
        elif pick != OPEN and not verbatim(quote, folded):
            entry['pick'], entry['why'] = INVALID, 'picked ' + pick + ' with a quote that does not occur in the text'
        picks[key] = entry
    missing = [t['term'] for t in terms['terms'] if fold(t['term']) not in picks]
    if missing:
        raise ValueError('no answer for the term(s) ' + ', '.join(repr(m) for m in missing))
    return {'session': session, 'readings': [picks[fold(t['term'])] for t in terms['terms']]}


def sessions_of(raw):
    """The sessions' canonical answers gathered by mh.aggregate (type text: one JSON object per line), by session."""
    out = {}
    for line in (raw or '').splitlines():
        if line.strip():
            s = json.loads(line)
            out[int(s['session'])] = s
    return out


# ==================== agreement ====================

def agree(terms, sessions, minimum=CONFIRM_MIN):
    """Decision 10's agreement. Per term: the picks of every session; a reading picked by >= minimum sessions is
    CONFIRMED (with the quotes those sessions gave); OPEN picked by >= minimum is OPEN (OPEN_BY_AGREEMENT); anything else
    is OPEN (NO_AGREEMENT). INVALID picks count for nothing. Returns {"terms": [...], "summary": {...}}."""
    order = sorted(sessions)
    rows = []
    for t in terms['terms']:
        key = fold(t['term'])
        picks = {}
        quotes = {}
        for s in order:
            entry = next((r for r in sessions[s]['readings'] if fold(r['term']) == key), None)
            pick = entry['pick'] if entry else INVALID
            picks[str(s)] = pick
            if entry and entry.get('quote') and pick not in (INVALID, OPEN):
                quotes.setdefault(pick, []).append(entry['quote'])
        counts = {}
        for p in picks.values():
            if p != INVALID:
                counts[p] = counts.get(p, 0) + 1
        winner = next((r for r in t['readings'] if counts.get(r['id'], 0) >= minimum), None)
        row = {'term': t['term'], 'picks': picks}
        if winner is not None:
            row.update({'status': CONFIRMED, 'readingId': winner['id'], 'reading': winner['reading'],
                        'quotes': list(dict.fromkeys(quotes.get(winner['id'], [])))})
        else:
            row.update({'status': OPEN, 'cause': OPEN_BY_AGREEMENT if counts.get(OPEN, 0) >= minimum else NO_AGREEMENT})
        row['unanimous'] = len(order) > 1 and len(set(picks.values())) == 1 and INVALID not in picks.values()
        rows.append(row)
    confirmed = sum(1 for r in rows if r['status'] == CONFIRMED)
    summary = {
        'sessions': order,
        'terms': len(rows),
        'confirmed': confirmed,
        'open': len(rows) - confirmed,
        'openByAgreement': sum(1 for r in rows if r.get('cause') == OPEN_BY_AGREEMENT),
        'noAgreement': sum(1 for r in rows if r.get('cause') == NO_AGREEMENT),
        'unanimous': sum(1 for r in rows if r['unanimous']),
        'invalidPicks': sum(1 for r in rows for p in r['picks'].values() if p == INVALID),
        'shareConfirmed': round(confirmed / len(rows), 2) if rows else None,
        'dropped': terms.get('dropped', []),
    }
    return {'terms': rows, 'summary': summary}


# ==================== the probe's meta-storage records ====================

TYPE_PREFIX = 'nrvv.concept-probe'
REC_KEY_FORMAT = 'term-NN (1-based, two digits, in the terms session\'s order), and summary'
BODY_FORMAT = ('JSON: per term its agreement {term, picks per session, status CONFIRMED|OPEN, readingId, reading, quotes '
               '| cause}; summary: the counts, the dropped terms, the label, every term with its readings')
CONSUMER = 'read by plan 050 Phase 2 (the go / no-go of decision 10); never consumed by NRVV; deleting it loses the measurement'


def type_name(exec_context_id):
    return TYPE_PREFIX + '.' + str(exec_context_id)


def is_synthetic(production):
    """Production is the literal 'true' only; anything else - null included - is the synthetic store."""
    return production is None or production.strip() != 'true'


def records_of(agreement, terms, rec_type, label):
    width = max(2, len(str(len(agreement['terms']))))
    records = [{'type': rec_type, 'recKey': 'term-' + str(i + 1).zfill(width), 'body': json.dumps(r, ensure_ascii=False)}
               for i, r in enumerate(agreement['terms'])]
    summary = dict(agreement['summary'], label=label, readings=terms['terms'])
    records.append({'type': rec_type, 'recKey': 'summary', 'body': json.dumps(summary, ensure_ascii=False)})
    return records


# ==================== the Functions ====================

def run_terms_prompt(task, function_code):
    inp = input_of(io.read_role(task, 'concept-input'))
    prompt = compose_terms(inp)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(function_code + ': ' + str(len(inp['needs'])) + ' NEED(s), ' + str(len(prompt)) + ' chars')


def run_terms_check(task, function_code):
    inp = input_of(io.read_role(task, 'concept-input'))
    terms = terms_of(io.read_role(task, 'cc-result'), inp)
    io.write_text(io.output_role(task, 'terms'), json.dumps(terms, ensure_ascii=False))
    io.write_text(io.output_role(task, 'sessions'), sessions_text())
    print(function_code + ': ' + str(len(terms['terms'])) + ' term(s): ' + ', '.join(t['term'] for t in terms['terms'])
          + '; dropped ' + str(len(terms['dropped'])))


def run_readings_prompt(task, function_code):
    inp = input_of(io.read_role(task, 'concept-input'))
    terms = terms_doc(io.read_role(task, 'terms'))
    session = session_of(io.read_role(task, 'session'))
    prompt = compose_readings(inp, terms, session)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(function_code + ': session ' + str(session) + ', ' + str(len(terms['terms'])) + ' term(s), '
          + str(len(prompt)) + ' chars')


def run_readings_check(task, function_code):
    inp = input_of(io.read_role(task, 'concept-input'))
    terms = terms_doc(io.read_role(task, 'terms'))
    session = session_of(io.read_role(task, 'session'))
    answer = readings_of(io.read_role(task, 'cc-result'), terms, inp, session)
    # one line: mh.aggregate joins the sessions' answers with a newline
    io.write_text(io.output_role(task, 'readings'), json.dumps(answer, ensure_ascii=False))
    print(function_code + ': session ' + str(session) + ': '
          + ', '.join(r['term'] + '=' + r['pick'] for r in answer['readings']))


def run_agree(task, function_code):
    terms = terms_doc(io.read_role(task, 'terms'))
    sessions = sessions_of(io.read_role(task, 'all-readings'))
    label = (io.read_role(task, 'label') or '').strip()
    agreement = agree(terms, sessions)
    rec_type = type_name(task['execContextId'])
    synthetic = is_synthetic(io.read_role(task, 'production'))
    io.write_text(io.output_role(task, 'records'), json.dumps(records_of(agreement, terms, rec_type, label),
                                                              ensure_ascii=False))
    io.write_text(io.output_role(task, 'summary'), json.dumps(dict(agreement, label=label), ensure_ascii=False))
    io.write_text(io.output_role(task, 'meta-storage-type'), rec_type)
    io.write_text(io.output_role(task, 'synthetic-flag'), 'true' if synthetic else 'false')
    io.write_text(io.output_role(task, 'table-desc'), 'Concept-probe agreement of ' + (label or 'an unnamed text') + ': '
                  + str(agreement['summary']['terms']) + ' terms, ' + str(agreement['summary']['confirmed'])
                  + ' confirmed, sessions ' + str(agreement['summary']['sessions']))
    io.write_text(io.output_role(task, 'table-rec-key-format'), REC_KEY_FORMAT)
    io.write_text(io.output_role(task, 'table-body-format'), BODY_FORMAT)
    io.write_text(io.output_role(task, 'table-consumer'), CONSUMER)
    s = agreement['summary']
    print(function_code + ': ' + label + ' - ' + str(s['terms']) + ' terms, ' + str(s['confirmed']) + ' confirmed, '
          + str(s['openByAgreement']) + ' open by agreement, ' + str(s['noAgreement']) + ' without agreement; '
          + 'type ' + rec_type + ', synthetic ' + str(synthetic))
