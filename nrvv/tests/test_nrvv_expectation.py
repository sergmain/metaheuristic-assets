# The expectation analysis (plan 047, Phase 6): the pieces the prompt lists, the prompt's tail, and every refusal of
# the check.

import json

import pytest

import nrvv_expectation as ex

R1 = ('# The Situation\n'
      '\n'
      'You have a central service that needs to publish gas price updates to gas stations.\n'
      '\n'
      'New desired prices keep arriving while earlier sends are still in flight.\n'
      '\n'
      'Only eventual correctness matters, where each station must settle on the latest price.\n'
      '\n'
      'Your sends can arrive at the station out of order, but all acknowledgements come back in order.\n'
      '\n'
      'Stations are dumb, you cannot add versioning / deduplication on their side.\n'
      '\n'
      'Sending has a COST -> don\'t spam, and avoid unnecessary updates.\n'
      'Not sending has a COST too! Stations act on stale prices.')


def expectation(text=R1, parent=None, needs=None):
    return {'expectationId': 12, 'parentId': parent, 'stakeholder': 'pricing team', 'text': text,
            'agreedNeeds': needs or []}


def span(text, sentence):
    start = text.index(sentence)
    return start, start + len(sentence)


def clause(frm, to, kind='OBLIGATION', **extra):
    c = {'from': frm, 'to': to, 'kind': kind, 'title': 'T', 'statement': 'The pricing team needs it.'}
    c.update(extra)
    return c


def answer(*clauses):
    return json.dumps({'clauses': list(clauses)})


# ==================== pieces ====================

def test_pieces_cover_r1_with_offsets_into_the_text():
    ps = ex.pieces(R1)
    assert ps[0] == (0, 15, '# The Situation')
    for frm, to, piece in ps:
        assert R1[frm:to] == piece, (frm, to, piece)
    texts = [p for _, _, p in ps]
    assert 'Sending has a COST -> don\'t spam,' in texts
    assert 'and avoid unnecessary updates.' in texts
    assert 'Not sending has a COST too!' in texts
    assert 'Stations act on stale prices.' in texts
    assert [p[0] for p in ps] == sorted(p[0] for p in ps)


def test_pieces_count_utf16_units():
    text = 'a \U0001F600 b. c'
    ps = ex.pieces(text)
    assert ps == [(0, 7, 'a \U0001F600 b.'), (8, 9, 'c')], 'the emoji is two UTF-16 units'
    assert ex.utf16_len(text) == 9


def test_pieces_single_character_and_blank_lines():
    assert ex.pieces('x\n\n  y  ') == [(0, 1, 'x'), (5, 6, 'y')]


# ==================== prompt ====================

def test_prompt_ends_with_the_answer_instruction():
    prompt = ex.compose(expectation())
    lines = prompt.split('\n')
    assert lines[-1] == ex.ANSWER_TAIL
    assert lines[-2] == ex.ANSWER_SHAPE
    assert lines[-3].startswith('Answer by calling the mh_cc_store_result tool exactly once')
    assert 'Print nothing' in lines[-1]
    assert prompt.index('[0,15) # The Situation') < prompt.index('mh_cc_store_result'), 'the instruction is LAST'


def test_prompt_lists_every_piece_with_its_offsets():
    prompt = ex.compose(expectation())
    for frm, to, piece in ex.pieces(R1):
        assert '[' + str(frm) + ',' + str(to) + ') ' + piece in prompt


def test_prompt_without_parent_asks_no_mapping():
    prompt = ex.compose(expectation())
    assert 'mapping' not in prompt
    assert 'The pricing team needs ...' in prompt
    assert 'no number, duration, rate or limit the text does not state' in prompt


def test_prompt_with_parent_lists_the_agreed_needs_and_asks_the_mapping():
    needs = [{'needReqId': 'GAS-3', 'title': 'Settle', 'statement': 'The pricing team needs\nstations to settle.',
              'kind': 'OBLIGATION'}]
    prompt = ex.compose(expectation(parent=11, needs=needs))
    assert 'NEED GAS-3 (OBLIGATION): Settle' in prompt
    assert '  The pricing team needs stations to settle.' in prompt
    assert 'mapping: UNCHANGED' in prompt
    assert prompt.split('\n')[-2] == ex.ANSWER_SHAPE_PARENT


# ==================== check: accepted ====================

def test_check_r1_five_clauses_in_canonical_order():
    a = span(R1, 'You have a central service that needs to publish gas price updates to gas stations.')
    b = span(R1, 'Only eventual correctness matters, where each station must settle on the latest price.')
    c = span(R1, 'Your sends can arrive at the station out of order, but all acknowledgements come back in order.')
    d = span(R1, 'Stations are dumb, you cannot add versioning / deduplication on their side.')
    e = (R1.index('Sending has a COST'), len(R1))
    raw = answer(clause(*e, kind='COST_OBJECTIVE'), clause(*a), clause(*b), clause(*c, kind='ENVIRONMENT_FACT'),
                 clause(*d, kind='SCOPE_LIMITER'))
    out = ex.clauses_of(raw, expectation())['clauses']
    assert [(x['from'], x['to']) for x in out] == [a, b, c, d, e]
    assert [x['kind'] for x in out] == ['OBLIGATION', 'OBLIGATION', 'ENVIRONMENT_FACT', 'SCOPE_LIMITER', 'COST_OBJECTIVE']
    assert all('mapping' not in x and 'needReqId' not in x for x in out)


def test_check_unwraps_one_fence_and_adjacent_spans_are_fine():
    raw = '```json\n' + answer(clause(0, 15), clause(15, 20)) + '\n```'
    assert len(ex.clauses_of(raw, expectation())['clauses']) == 2


def test_check_with_parent_keeps_mapping_and_need():
    needs = [{'needReqId': 'GAS-3'}, {'needReqId': 'GAS-4'}]
    raw = answer(clause(0, 10, mapping='AMENDS', needReqId='GAS-3'), clause(20, 30, mapping='NEW', needReqId=None),
                 clause(40, 50, mapping='UNCHANGED', needReqId='GAS-4'))
    out = ex.clauses_of(raw, expectation(parent=11, needs=needs))['clauses']
    assert [(x['mapping'], x['needReqId']) for x in out] == [('AMENDS', 'GAS-3'), ('NEW', None), ('UNCHANGED', 'GAS-4')]


# ==================== check: refused ====================

NEEDS = [{'needReqId': 'GAS-3'}]


@pytest.mark.parametrize('raw, parent, message', [
    ('not json', None, 'not JSON'),
    (json.dumps({'findings': []}), None, 'no {"clauses"'),
    (json.dumps({'clauses': [], 'x': 1}), None, 'no {"clauses"'),
    (answer(), None, 'no clause'),
    (answer(clause(0, 10, quote='x')), None, 'unknown field'),
    (answer(clause('0', 10)), None, 'integer'),
    (answer(clause(True, 10)), None, 'integer'),
    (answer(clause(-1, 10)), None, 'not inside'),
    (answer(clause(0, len(R1) + 1)), None, 'not inside'),
    (answer(clause(10, 10)), None, 'empty'),
    (answer(clause(0, 10), clause(5, 15)), None, 'overlap'),
    (answer(clause(0, 10, kind='WISH')), None, 'unknown kind'),
    (answer(dict(clause(0, 10), title=' ')), None, 'no title'),
    (answer(dict(clause(0, 10), title='t' * 251)), None, 'over 250'),
    (answer(dict(clause(0, 10), statement='')), None, 'empty statement'),
    (answer(clause(0, 10, mapping='NEW')), None, 'no parent'),
    (answer(clause(0, 10, needReqId='GAS-3')), None, 'no parent'),
    (answer(clause(0, 10)), 11, 'unknown mapping'),
    (answer(clause(0, 10, mapping='AMENDS')), 11, 'names no agreed NEED'),
    (answer(clause(0, 10, mapping='AMENDS', needReqId='GAS-9')), 11, 'names no agreed NEED'),
    (answer(clause(0, 10, mapping='UNCHANGED', needReqId=None)), 11, 'names no agreed NEED'),
    (answer(clause(0, 10, mapping='NEW', needReqId='GAS-3')), 11, 'is NEW and names'),
    (answer(clause(0, 10, mapping='AMENDS', needReqId='GAS-3'), clause(20, 30, mapping='UNCHANGED', needReqId='GAS-3')),
     11, 'second time'),
])
def test_check_refuses(raw, parent, message):
    with pytest.raises(ValueError) as e:
        ex.clauses_of(raw, expectation(parent=parent, needs=NEEDS if parent else None))
    assert message in str(e.value)


@pytest.mark.parametrize('raw', [
    'not json',
    json.dumps({'text': ''}),
    json.dumps({'text': 'x', 'agreedNeeds': {}}),
    json.dumps({'text': 'x', 'agreedNeeds': [{'title': 'no reqId'}]}),
])
def test_expectation_of_refuses(raw):
    with pytest.raises(ValueError):
        ex.expectation_of(raw)


def test_expectation_of_defaults_the_agreed_needs():
    assert ex.expectation_of(json.dumps({'text': 'x', 'parentId': None}))['agreedNeeds'] == []
