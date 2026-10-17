# The evidence rules (nrvv_evidence) on the shared table of cases, tests/data/evidence-cases.json - the same table the
# Dispatcher's re-check is tested on; the coverage cases there are the Dispatcher's alone.

import json
import os
import re

import pytest

import nrvv_evidence as ev

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'evidence-cases.json'), encoding='utf-8') as f:
    TABLE = json.load(f)

STATEMENTS = {n['reqId']: n['statement'] for n in TABLE['needs']}
STATEMENTS.update({i['reqId']: i['statement'] for i in TABLE['items']})
KINDS = {n['reqId']: n['kind'] for n in TABLE['needs']}
RULE = re.compile(r'rule (\d) \(')


def rule_of(refusal):
    if refusal is None:
        return None
    m = RULE.search(refusal)
    assert m, 'a refusal names no rule: ' + refusal
    return int(m.group(1))


def citations(needs):
    return [n + ' r1' for n in needs]


@pytest.mark.parametrize('case', TABLE['topLevel'], ids=[c['id'] for c in TABLE['topLevel']])
def test_top_level_case(case):
    evidence = [(e['source'], e['quote']) for e in case['evidence']]
    text = ev.rationale(citations(case['needs']), None, [], case['readings'], evidence, [], case['prose'])
    parsed = ev.parse_evidence(text)
    assert parsed == evidence, 'the evidence lines read back'
    sources = {r: STATEMENTS[r] for r in case['needs'] + case['readings']}
    kinds = [KINDS[n] for n in case['needs'] if ev.is_derivation_subject(KINDS[n])]
    refusal = ev.top_level_refusal(case['key'], case['statement'], text, parsed, sources, kinds)
    assert rule_of(refusal) == case['refusedBy'], refusal
    if refusal is not None:
        assert refusal.startswith(case['key'] + ': rule ' + str(case['refusedBy']) + ' ('), refusal


@pytest.mark.parametrize('case', TABLE['interpretation'], ids=[c['id'] for c in TABLE['interpretation']])
def test_interpretation_case(case):
    evidence = [(e['source'], e['quote']) for e in case['evidence']]
    governs = [] if case['kind'] == 'ASSUMPTION' else ['GASV6A3-4']
    text = ev.rationale(citations(case['needs']), case['kind'], governs, [], evidence, [], case['prose'])
    sources = {r: STATEMENTS[r] for r in case['needs']}
    refusal = ev.interpretation_refusal(case['key'], case['kind'], case['statement'], text, ev.parse_evidence(text), sources)
    assert rule_of(refusal) == case['refusedBy'], refusal


@pytest.mark.parametrize('case', TABLE['language'], ids=[c['text'] for c in TABLE['language']])
def test_language_case(case):
    assert (ev.language_refusal('X-1', case['text']) is not None) == case['refused']


@pytest.mark.parametrize('case', TABLE['normalize'], ids=[c['in'] for c in TABLE['normalize']])
def test_normalize_case(case):
    assert ev.normalize(case['in']) == case['out']


def test_rationale_writes_the_lines_in_their_order():
    text = ev.rationale(['GASV6A3-4 r1', 'GASV6A3-3 r1'], 'READING', ['GASV6A3-1'], ['GASV7R-12'],
                        [('GASV6A3-3', 'only eventual correctness to matter')], ['how soon is not stated'], 'The prose.')
    assert text == ('need: GASV6A3-4 r1, GASV6A3-3 r1\n'
                    'interpretation: READING\n'
                    'governs: GASV6A3-1\n'
                    'reading: GASV7R-12\n'
                    'evidence: GASV6A3-3 "only eventual correctness to matter"\n'
                    'ambiguity: how soon is not stated\n'
                    'The prose.')


def test_parse_list_reads_the_first_line_of_its_label():
    text = 'need: GASV6A3-4 r1, GASV6A3-3 r1\n  Governs: *\nreading: GASV7R-12, GASV7R-13, GASV7R-12\nreading: X-9'
    assert ev.parse_list(text, 'need') == ['GASV6A3-4 r1', 'GASV6A3-3 r1']
    assert ev.parse_list(text, 'governs') == ['*']
    assert ev.parse_list(text, 'reading') == ['GASV7R-12', 'GASV7R-13']
    assert ev.parse_list(text, 'interpretation') == []
    assert ev.parse_list(None, 'need') == []


def test_parse_evidence_skips_a_line_of_another_shape():
    text = ('evidence: GASV6A3-3 "only eventual correctness to matter"\nevidence: no quote here\n'
            '  EVIDENCE:   GASV6A3-4   "each station to settle"  \nthe prose mentions evidence: X "y z" inside')
    assert ev.parse_evidence(text) == [('GASV6A3-3', 'only eventual correctness to matter'),
                                       ('GASV6A3-4', 'each station to settle')]


def test_cost_rule_applies_only_when_every_cited_subject_is_a_cost():
    s = 'The service shall send at most one update per price change.'
    assert ev.cost_refusal('T-1', s, []) is None
    assert ev.cost_refusal('T-1', s, ['COST_OBJECTIVE', 'OBLIGATION']) is None
    assert ev.cost_refusal('T-1', s, ['COST_OBJECTIVE']) is not None
    assert ev.cost_refusal('T-1', 'The service shall measure and report the cost of not sending.', ['COST_OBJECTIVE']) is None


def test_word_lists_are_the_planned_ones():
    assert ev.UNIVERSAL_WORDS == {'each', 'every', 'all', 'any', 'always', 'never'}
    assert len(ev.COST_PHRASES) == 10 and len(ev.COST_WORDS) == 12 and len(ev.LANGUAGE_NAMES) == 16
