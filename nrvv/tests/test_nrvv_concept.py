# Concept analysis (plan 050 decision 10, Phase 2): the terms prompt and check, the rotated readings prompt and check, the
# deterministic agreement, the probe's meta-storage records, and the five Functions on a Task's working dir.

import json
import os

import pytest

import nrvv_concept as wf

INPUT = {
    'expectation': 'Members borrow books from the library.\nA book must be returned on time; a late book costs a fee.\n'
                   'Renewals are allowed when nobody waits for the book.',
    'needs': [
        {'reqId': 'LIB-2', 'kind': 'OBLIGATION', 'title': 'Return on time',
         'statement': 'The library needs every book returned on time.'},
        {'reqId': 'LIB-3', 'kind': 'COST_OBJECTIVE', 'title': 'Late fee', 'statement': 'A late book costs a fee.'},
        {'reqId': 'LIB-4', 'kind': 'OBLIGATION', 'title': 'Renewals',
         'statement': 'The library needs renewals allowed when nobody waits for the book.'},
    ],
}
RAW = json.dumps(INPUT)


def terms_answer(*terms):
    return json.dumps({'terms': list(terms)})


def term(name, *readings):
    return {'term': name, 'readings': [{'reading': r, 'quote': q} for r, q in readings]}


RETURNED = term('returned', ('dropped in the return box', 'returned on time'),
                ('checked in at the desk', 'every book returned on time'))
ON_TIME = term('on time', ('by the due date', 'must be returned on time'), ('before the fee applies', 'a late book costs a fee'),
               ('within the loan period of the renewal', 'Renewals are allowed'))


def canonical(*answer_terms):
    return wf.terms_of(terms_answer(*answer_terms), INPUT)


# ==================== input and verbatim ====================

@pytest.mark.parametrize('raw, message', [
    ('not json', 'not JSON'),
    ('[]', 'not an object'),
    (json.dumps({'expectation': ' ', 'needs': []}), 'no expectation text'),
    (json.dumps({'expectation': 'x'}), 'no list of NEEDs'),
    (json.dumps({'expectation': 'x', 'needs': [{'reqId': 'A-1'}]}), 'NEED #0 of the concept input has no reqId or no statement'),
])
def test_inputOf_refusesABrokenInput(raw, message):
    with pytest.raises(ValueError) as e:
        wf.input_of(raw)
    assert message in str(e.value)


def test_inputOf_acceptsTheShape():
    assert wf.input_of(RAW)['needs'][1]['reqId'] == 'LIB-3'


def test_verbatim_foldsCaseQuotesAndWhitespace():
    corpus = wf.corpus(INPUT)
    assert wf.verbatim('A book  must be\nRETURNED on time', corpus)
    assert wf.verbatim('\u201cRenewals are allowed', '"renewals are allowed when')
    assert not wf.verbatim('returned late', corpus)
    assert not wf.verbatim('   ', corpus)


def test_corpus_holdsTheNeedTitlesAndStatements():
    assert wf.verbatim('Late fee', wf.corpus(INPUT))
    assert wf.verbatim('The library needs every book returned on time.', wf.corpus(INPUT))


# ==================== terms ====================

def test_composeTerms_showsTheTextAndEndsWithTheAnswerInstruction():
    prompt = wf.compose_terms(INPUT)
    assert '> Members borrow books from the library.' in prompt
    assert 'NEED LIB-3 (COST_OBJECTIVE): Late fee' in prompt
    assert prompt.rstrip().endswith(wf.ANSWER_TAIL)
    assert prompt.index(wf.TERMS_SHAPE) > prompt.index('NEED LIB-4')


@pytest.mark.parametrize('compose', [
    lambda: wf.compose_terms(INPUT),
    lambda: wf.compose_readings(INPUT, canonical(RETURNED), 1),
])
def test_thePrompts_carryNoneOfTheGasPriceWords(compose):
    # plan 050 Phase 2 measures whether the probe FINDS r1's words; a prompt naming them would hand it the answer
    prompt = compose().lower()
    for word in ('publish', 'settle', 'in order', 'unnecessary update', 'lapse', 'acknowledg', 'station', 'price'):
        assert word not in prompt, word


def test_termsOf_lettersTheReadingsInTheOrderAnswered():
    t = canonical(RETURNED, ON_TIME)
    assert [x['term'] for x in t['terms']] == ['returned', 'on time']
    assert [r['id'] for r in t['terms'][1]['readings']] == ['A', 'B', 'C']
    assert t['terms'][0]['readings'][1] == {'id': 'B', 'reading': 'checked in at the desk', 'quote': 'every book returned on time'}
    assert t['dropped'] == []


def test_termsOf_dropsATermThatIsNotInTheText():
    t = canonical(RETURNED, term('overdue', ('past the due date', 'returned on time'), ('fined', 'costs a fee')))
    assert [x['term'] for x in t['terms']] == ['returned']
    assert t['dropped'] == [{'term': 'overdue', 'why': 'the term does not occur in the text'}]


def test_termsOf_setsAsideAReadingWhoseQuoteIsNotInTheText_andDropsATermLeftWithOne():
    t = canonical(RETURNED, term('late', ('after the due date', 'a late book'), ('after closing time', 'closes at six')))
    assert [x['term'] for x in t['terms']] == ['returned']
    assert t['dropped'] == [{'term': 'late', 'why': 'reading #1: its quote does not occur in the text'},
                            {'term': 'late', 'why': 'fewer than 2 readings'}]


def test_termsOf_aTermListedTwice_isKeptOnce():
    t = canonical(RETURNED, dict(RETURNED, term='Returned'))
    assert [x['term'] for x in t['terms']] == ['returned']
    assert t['dropped'] == [{'term': 'Returned', 'why': 'listed twice'}]


def test_termsOf_keepsAtMostFourReadingsAndAtMostTheTermCap():
    five = term('on time', *[('reading ' + str(i), 'on time') for i in range(5)])
    t = canonical(five)
    assert [r['id'] for r in t['terms'][0]['readings']] == ['A', 'B', 'C', 'D']
    many = [term('book', ('r1 ' + str(i), 'book'), ('r2 ' + str(i), 'books')) for i in range(wf.MAX_TERMS)]
    many = [dict(m, term=w) for m, w in zip(many, ['book', 'books', 'library', 'late', 'fee', 'members', 'borrow',
                                                   'renewals', 'allowed', 'waits', 'nobody', 'return', 'on time', 'costs',
                                                   'must', 'every', 'needs', 'Late fee', 'Renewals are allowed',
                                                   'a late book', 'from the library', 'returned', 'waits for',
                                                   'Return on time'])]
    t = wf.terms_of(terms_answer(*many, term('a fee', ('x', 'a fee'), ('y', 'costs a fee'))), INPUT)
    assert len(t['terms']) == wf.MAX_TERMS
    assert t['dropped'][-1] == {'term': 'a fee', 'why': 'more than 24 terms'}


def test_termsOf_acceptsAFencedAnswer():
    assert len(wf.terms_of('```json\n' + terms_answer(RETURNED) + '\n```', INPUT)['terms']) == 1


@pytest.mark.parametrize('answer, message', [
    ('nothing', 'not JSON'),
    (json.dumps({'terms': [], 'more': 1}), 'no {"terms": [...]} object'),
    (json.dumps({'terms': [{'term': 'returned', 'readings': [], 'kind': 'x'}]}), "unknown field 'kind'"),
    (json.dumps({'terms': [{'term': '', 'readings': []}]}), 'has no term'),
    (json.dumps({'terms': [{'term': 'returned', 'readings': [{'reading': 'x', 'quote': 'y', 'id': 'A'}]}]}),
     'is not an object of reading and quote'),
    (terms_answer(term('overdue', ('a', 'b'), ('c', 'd'))), 'CC listed no usable term'),
])
def test_termsOf_refusesAWrongShape(answer, message):
    with pytest.raises(ValueError) as e:
        wf.terms_of(answer, INPUT)
    assert message in str(e.value)


def test_sessionsText_isOneNumberPerLine():
    assert wf.sessions_text() == '1\n2\n3'


# ==================== readings ====================

def test_sessionOf():
    assert wf.session_of('2\n') == 2
    for bad in ('', '0', '1\n2', 'x'):
        with pytest.raises(ValueError):
            wf.session_of(bad)


def test_rotated_movesTheListLeftBySessionMinusOne():
    rs = ['A', 'B', 'C']
    assert (wf.rotated(rs, 1), wf.rotated(rs, 2), wf.rotated(rs, 3), wf.rotated(rs, 4)) == (
        ['A', 'B', 'C'], ['B', 'C', 'A'], ['C', 'A', 'B'], ['A', 'B', 'C'])
    assert wf.rotated(['A', 'B'], 3) == ['A', 'B']
    assert wf.rotated([], 2) == []


def test_composeReadings_listsTheReadingsRotatedWithTheirLetters():
    t = canonical(ON_TIME)
    one, two = wf.compose_readings(INPUT, t, 1), wf.compose_readings(INPUT, t, 2)
    assert one.index('  A: by the due date') < one.index('  B: before the fee applies')
    assert two.index('  B: before the fee applies') < two.index('  C: within') < two.index('  A: by the due date')
    assert 'Term "on time":' in one and one.rstrip().endswith(wf.ANSWER_TAIL)
    assert one.replace('\n', '') != two.replace('\n', '')


def readings_answer(*entries):
    return json.dumps({'readings': [dict(zip(('term', 'pick', 'quote'), e)) for e in entries]})


def test_readingsOf_canonicalInTermOrder_withInvalidPicksRecorded():
    t = canonical(RETURNED, ON_TIME)
    out = wf.readings_of(readings_answer(('ON TIME', 'z', 'on time'), ('returned', 'b', 'every book returned on time')),
                         t, INPUT, 2)
    assert out == {'session': 2, 'readings': [
        {'term': 'returned', 'pick': 'B', 'quote': 'every book returned on time'},
        {'term': 'on time', 'pick': 'INVALID', 'quote': 'on time', 'why': "answered 'z', no letter of this term"}]}


def test_readingsOf_aPickWithAQuoteNotInTheText_isInvalid_andOpenNeedsNoQuote():
    t = canonical(RETURNED, ON_TIME)
    out = wf.readings_of(json.dumps({'readings': [{'term': 'returned', 'pick': 'A', 'quote': 'in the box'},
                                                  {'term': 'on time', 'pick': 'OPEN'}]}), t, INPUT, 1)
    assert out['readings'][0]['pick'] == 'INVALID' and 'does not occur in the text' in out['readings'][0]['why']
    assert out['readings'][1] == {'term': 'on time', 'pick': 'OPEN'}


@pytest.mark.parametrize('answer, message', [
    (readings_answer(('returned', 'A', 'returned on time')), "no answer for the term(s) 'on time'"),
    (readings_answer(('returned', 'A', 'x'), ('returned', 'B', 'y')), 'a second time'),
    (readings_answer(('overdue', 'A', 'x')), 'which is not listed'),
    (json.dumps({'readings': [{'term': 'returned', 'pick': 'A', 'why': 'x'}]}), "unknown field 'why'"),
])
def test_readingsOf_refusesAWrongShape(answer, message):
    with pytest.raises(ValueError) as e:
        wf.readings_of(answer, canonical(RETURNED, ON_TIME), INPUT, 1)
    assert message in str(e.value)


def test_sessionsOf_readsOneObjectPerLine():
    raw = json.dumps({'session': 2, 'readings': []}) + '\n\n' + json.dumps({'session': 1, 'readings': []}) + '\n'
    assert sorted(wf.sessions_of(raw)) == [1, 2]


# ==================== agreement ====================

def sessions(*per_session):
    """per_session: for each session, (pick, quote) per term in RETURNED, ON_TIME order."""
    out = {}
    for s, picks in enumerate(per_session, start=1):
        rows = []
        for name, (pick, quote) in zip(['returned', 'on time'], picks):
            row = {'term': name, 'pick': pick}
            if quote:
                row['quote'] = quote
            rows.append(row)
        out[s] = {'session': s, 'readings': rows}
    return out


def terms2():
    return canonical(RETURNED, ON_TIME)


def test_agree_threeAgreeing_isConfirmedAndUnanimous():
    a = wf.agree(terms2(), sessions([('B', 'returned on time'), ('A', 'must be returned on time')],
                                    [('B', 'every book returned on time'), ('A', 'must be returned on time')],
                                    [('B', 'returned on time'), ('A', 'must be returned on time')]))
    first = a['terms'][0]
    assert (first['status'], first['readingId'], first['reading'], first['unanimous']) == (
        'CONFIRMED', 'B', 'checked in at the desk', True)
    assert first['quotes'] == ['returned on time', 'every book returned on time'], 'the quotes verbatim, each once'
    assert first['picks'] == {'1': 'B', '2': 'B', '3': 'B'}
    assert (a['summary']['confirmed'], a['summary']['unanimous'], a['summary']['shareConfirmed']) == (2, 2, 1.0)


def test_agree_twoOfThree_confirms_threeDifferent_isOpenWithoutAgreement():
    a = wf.agree(terms2(), sessions([('A', 'returned on time'), ('A', 'on time')],
                                    [('A', 'returned on time'), ('B', 'a late book costs a fee')],
                                    [('OPEN', None), ('C', 'Renewals are allowed')]))
    assert (a['terms'][0]['status'], a['terms'][0]['readingId'], a['terms'][0]['unanimous']) == ('CONFIRMED', 'A', False)
    assert (a['terms'][1]['status'], a['terms'][1]['cause']) == ('OPEN', 'NO_AGREEMENT')
    assert (a['summary']['confirmed'], a['summary']['noAgreement'], a['summary']['shareConfirmed']) == (1, 1, 0.5)


def test_agree_openByTwo_isOpenByAgreement():
    a = wf.agree(terms2(), sessions([('OPEN', None), ('OPEN', None)], [('OPEN', 'returned on time'), ('A', 'on time')],
                                    [('A', 'returned on time'), ('OPEN', None)]))
    assert [(r['status'], r['cause']) for r in a['terms']] == [('OPEN', 'OPEN_BY_AGREEMENT'), ('OPEN', 'OPEN_BY_AGREEMENT')]
    assert a['summary']['openByAgreement'] == 2


def test_agree_invalidPicksCountForNothing():
    a = wf.agree(terms2(), sessions([('A', 'x'), ('INVALID', 'x')], [('INVALID', 'x'), ('INVALID', 'x')],
                                    [('B', 'x'), ('A', 'x')]))
    assert [r.get('cause') for r in a['terms']] == ['NO_AGREEMENT', 'NO_AGREEMENT']
    assert a['summary']['invalidPicks'] == 3


def test_agree_withTwoSessionsLeft_twoAgreeingStillConfirm():
    s = sessions([('A', 'returned on time'), ('A', 'on time')], [('A', 'returned on time'), ('B', 'a fee')])
    a = wf.agree(terms2(), s)
    assert [r['status'] for r in a['terms']] == ['CONFIRMED', 'OPEN']
    assert a['summary']['sessions'] == [1, 2]


def test_agree_carriesTheDroppedTermsIntoTheSummary():
    t = canonical(RETURNED, ON_TIME, term('overdue', ('a', 'b'), ('c', 'd')))
    a = wf.agree(t, sessions([('A', 'x'), ('A', 'x')]))
    assert a['summary']['dropped'] == [{'term': 'overdue', 'why': 'the term does not occur in the text'}]


# ==================== records ====================

def test_recordsOf_oneRecordPerTermThenTheSummary():
    t = terms2()
    a = wf.agree(t, sessions([('A', 'returned on time'), ('A', 'on time')], [('A', 'returned on time'), ('A', 'on time')]))
    recs = wf.records_of(a, t, 'nrvv.concept-probe.7', 'r1')
    assert [r['recKey'] for r in recs] == ['term-01', 'term-02', 'summary']
    assert {r['type'] for r in recs} == {'nrvv.concept-probe.7'}
    summary = json.loads(recs[-1]['body'])
    assert (summary['label'], summary['confirmed'], len(summary['readings'])) == ('r1', 2, 2)
    assert json.loads(recs[0]['body'])['term'] == 'returned'


def test_isSynthetic_onlyTheLiteralTrueIsProduction():
    assert [wf.is_synthetic(p) for p in (None, '', 'True', 'false', ' true ')] == [True, True, True, True, False]


# ==================== the Functions ====================

def _task(tmp_path, metas, inputs, outputs, exec_context_id=4242):
    work = tmp_path / 'work'
    vars_in = []
    for i, (name, text) in enumerate(inputs.items()):
        var = {'name': name, 'id': i + 1, 'dataType': 'variable'}
        if text is None:
            var['empty'] = True
        else:
            p = work / 'variable' / str(i + 1)
            os.makedirs(p.parent, exist_ok=True)
            p.write_text(text, encoding='utf-8')
        vars_in.append(var)
    return {'workingPath': str(work), 'execContextId': exec_context_id, 'metas': [{k: v} for k, v in metas.items()],
            'inputs': vars_in, 'outputs': [{'name': n, 'id': 100 + i} for i, n in enumerate(outputs)]}


def _out(tmp_path, index):
    return (tmp_path / 'work' / 'artifacts' / str(100 + index)).read_text(encoding='utf-8')


def test_theFunctions_endToEnd(tmp_path):
    # terms prompt
    task = _task(tmp_path / 'tp', {'variable-for-concept-input': 'conceptInput', 'variable-for-prompt': 'termsPrompt'},
                 {'conceptInput': RAW}, ['termsPrompt'])
    wf.run_terms_prompt(task, 'tp')
    assert 'NEED LIB-2' in _out(tmp_path / 'tp', 0)
    # terms check
    task = _task(tmp_path / 'tc', {'variable-for-concept-input': 'conceptInput', 'variable-for-cc-result': 'termsResult',
                                   'variable-for-terms': 'terms', 'variable-for-sessions': 'sessions'},
                 {'conceptInput': RAW, 'termsResult': terms_answer(RETURNED, ON_TIME)}, ['terms', 'sessions'])
    wf.run_terms_check(task, 'tc')
    terms_json = _out(tmp_path / 'tc', 0)
    assert _out(tmp_path / 'tc', 1) == '1\n2\n3'
    # one readings session: prompt and check
    lines = []
    for s, picks in ((1, ('B', 'A')), (2, ('B', 'OPEN')), (3, ('A', 'OPEN'))):
        d = tmp_path / ('r' + str(s))
        task = _task(d, {'variable-for-concept-input': 'conceptInput', 'variable-for-terms': 'terms',
                         'variable-for-session': 'sessionChunk', 'variable-for-prompt': 'readingsPrompt'},
                     {'conceptInput': RAW, 'terms': terms_json, 'sessionChunk': str(s) + '\n'}, ['readingsPrompt'])
        wf.run_readings_prompt(task, 'rp')
        assert 'Term "returned":' in _out(d, 0)
        answer = readings_answer(('returned', picks[0], 'returned on time'), ('on time', picks[1], 'on time'))
        task = _task(d / 'c', {'variable-for-concept-input': 'conceptInput', 'variable-for-terms': 'terms',
                               'variable-for-session': 'sessionChunk', 'variable-for-cc-result': 'readingsResult',
                               'variable-for-readings': 'readings'},
                     {'conceptInput': RAW, 'terms': terms_json, 'sessionChunk': str(s), 'readingsResult': answer},
                     ['readings'])
        wf.run_readings_check(task, 'rc')
        line = _out(d / 'c', 0)
        assert '\n' not in line, 'one line per session - mh.aggregate joins them by newline'
        lines.append(line)
    # agree, over what mh.aggregate (type text) gathers; label and production nullified
    roles = ['records', 'summary', 'meta-storage-type', 'synthetic-flag', 'table-desc', 'table-rec-key-format',
             'table-body-format', 'table-consumer']
    names = ['conceptRecords', 'conceptSummary', 'metaStorageType', 'syntheticFlag', 'tableDesc', 'tableRecKeyFormat',
             'tableBodyFormat', 'tableConsumer']
    metas = {'variable-for-terms': 'terms', 'variable-for-all-readings': 'allReadings', 'variable-for-label': 'probeLabel',
             'variable-for-production': 'production'}
    metas.update({'variable-for-' + r: n for r, n in zip(roles, names)})
    task = _task(tmp_path / 'ag', metas, {'terms': terms_json, 'allReadings': '\n'.join(lines), 'probeLabel': None,
                                          'production': None}, names, exec_context_id=3001)
    wf.run_agree(task, 'ag')
    records = json.loads(_out(tmp_path / 'ag', 0))
    assert [r['recKey'] for r in records] == ['term-01', 'term-02', 'summary']
    summary = json.loads(_out(tmp_path / 'ag', 1))
    assert [(t['term'], t['status'], t.get('readingId'), t.get('cause')) for t in summary['terms']] == [
        ('returned', 'CONFIRMED', 'B', None), ('on time', 'OPEN', None, 'OPEN_BY_AGREEMENT')]
    assert (_out(tmp_path / 'ag', 2), _out(tmp_path / 'ag', 3)) == ('nrvv.concept-probe.3001', 'true')
    assert 'an unnamed text' in _out(tmp_path / 'ag', 4)
