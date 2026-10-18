# The definition under the NEED interpretation, by parts (nrvv_definition_interpreted) - its prompts and checks, on r1's
# agreed NEEDs from tests/data/evidence-cases.json.

import json
import os

import pytest

import nrvv_definition_interpreted as wf

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'evidence-cases.json'), encoding='utf-8') as f:
    TABLE = json.load(f)


def n(i):
    return 'GASV6A3-' + str(i)


NEED = {x['reqId']: {'reqId': x['reqId'], 'revision': x['revision'], 'kind': x['kind'], 'title': 'T ' + x['reqId'],
                     'statement': x['statement']} for x in TABLE['needs']}
READING = {'reqId': 'I-12', 'kind': 'READING', 'governs': [n(1)], 'needs': [n(1), n(3), n(9)],
           'statement': 'Publishing an update is met when the station ends up holding the latest desired price; a price'
                        ' superseded before delivery need not be delivered.'}
ASSUMPTIONS = [{'reqId': 'I-13', 'kind': 'ASSUMPTION', 'governs': [], 'needs': [n(5)],
                'statement': 'Sends can arrive at a station out of order.'},
               {'reqId': 'I-14', 'kind': 'ASSUMPTION', 'governs': [], 'needs': [n(6)],
                'statement': 'All acknowledgements come back in order.'}]
OPEN = {'reqId': 'I-15', 'kind': 'OPEN_CHOICE', 'governs': [n(4)], 'needs': [n(3), n(4)],
        'statement': 'How soon a station holds the latest price is not stated.'}

DEFINITION_INPUT = {'subjects': [
    {'need': NEED[n(1)], 'readings': [READING], 'needs': [NEED[n(3)], NEED[n(9)]]},
    {'need': NEED[n(9)], 'readings': [], 'needs': []},
]}
TOPS = [{'reqId': 'T-21', 'title': 'Publish', 'statement': 'The central service shall publish to each station the price it is to hold.',
         'rationale': 'r'},
        {'reqId': 'T-22', 'title': 'Settle', 'statement': 'Every station shall eventually hold the latest desired price.',
         'rationale': 'r'}]
BOUNDARY_INPUT = {'requirements': TOPS, 'items': ASSUMPTIONS + [OPEN]}
DESIGN_INPUT = {'requirements': TOPS, 'items': [READING] + ASSUMPTIONS + [OPEN]}


def top(key='GASV6A3-1-1', needs=None, readings=None, statement=None, evidence=None, rationale='Read through I-12.', **extra):
    item = {'key': key, 'needs': needs if needs is not None else [n(1), n(3)], 'readings': readings if readings is not None else ['I-12'],
            'title': 'Publish the price a station is to hold',
            'statement': statement or 'The central service shall publish to a station the newest price it is to hold.',
            'rationale': rationale,
            'evidence': evidence if evidence is not None else [{'source': n(1), 'quote': 'publish gas price updates to gas stations'},
                                                               {'source': n(3), 'quote': 'only eventual correctness to matter'}]}
    item.update(extra)
    return item


def answer(**lists):
    return json.dumps(lists)


def refused_top(items, subject=n(1)):
    out = wf.check_top(answer(requirements=items), DEFINITION_INPUT, subject)
    assert 'refused' in out, out
    return out['refused']


# ---- TOP-LEVEL ----

def test_top_prompt_reads_the_subject_through_its_items_and_ends_with_the_answer():
    p = wf.compose_top(DEFINITION_INPUT, n(1))
    assert 'Read the subject THROUGH the interpretation items that govern it' in p
    assert '- I-12 READING governing ' + n(1) in p
    assert 'NEED ' + n(3) + ' (revision 1, SCOPE_LIMITER)' in p, 'the NEEDs the items cite'
    for rule in wf.V5_RULES + wf.EVIDENCE_RULES:
        assert rule in p
    assert p.splitlines()[-1].startswith('Print nothing')
    assert p.splitlines()[-3].startswith('Answer by calling the mh_cc_store_result tool exactly once')


def test_top_check_accepts_and_canonicalises():
    out = wf.check_top(answer(requirements=[top()]), DEFINITION_INPUT, n(1))
    assert 'refused' not in out, out
    assert out['requirements'][0]['readings'] == ['I-12']
    assert out['requirements'][0]['evidence'][0] == {'source': n(1), 'quote': 'publish gas price updates to gas stations'}


def test_top_check_quotes_a_followed_item():
    item = top(statement='The central service need not deliver a price superseded before delivery.',
               evidence=[{'source': 'I-12', 'quote': 'a price superseded before delivery need not be delivered'}])
    assert 'refused' not in wf.check_top(answer(requirements=[item]), DEFINITION_INPUT, n(1))


def test_top_check_refuses_the_three_v6_statements():
    assert 'rule 2 (universal word)' in refused_top([top(needs=[n(1)], readings=[],
        statement='The service shall publish each gas price update to gas stations.',
        evidence=[{'source': n(1), 'quote': 'publish gas price updates to gas stations'}])])
    assert 'rule 4 (cost)' in wf.check_top(answer(requirements=[top(key='GASV6A3-9-1', needs=[n(9)], readings=[],
        statement='The service shall not send a price update to a station that is already known to hold the desired price.',
        evidence=[{'source': n(9), 'quote': 'unnecessary updates avoided'}])]), DEFINITION_INPUT, n(9))['refused']


def test_top_check_refuses_by_rule_1_and_rule_5():
    assert 'rule 1 (quote)' in refused_top([top(evidence=[{'source': n(1), 'quote': 'publish gas price changes to gas stations'}])])
    assert 'rule 1 (quote)' in refused_top([top(evidence=[])])
    assert 'rule 5 (language)' in refused_top([top(statement='The central service shall publish prices from a Python process.')])


def test_top_check_refuses_needs_readings_and_an_uncited_subject():
    assert 'outside the subject' in refused_top([top(needs=[n(1), n(5)])])
    assert 'are not items governing' in refused_top([top(readings=['I-13'])])
    assert 'no requirement cites the subject' in refused_top([top(needs=[n(3)], evidence=[{'source': n(3),
                                                                   'quote': 'only eventual correctness to matter'}])])


def test_top_check_refuses_assumed_unknown_field_and_shape():
    assert 'assumed:' in refused_top([top(rationale='assumed: the network is fast')])
    assert 'unknown field' in refused_top([top(why='x')])
    assert 'is not {"requirements"' in wf.check_top(answer(requirements=[], more=[]), DEFINITION_INPUT, n(1))['refused']
    assert 'holds no requirement' in wf.check_top(answer(requirements=[]), DEFINITION_INPUT, n(1))['refused']
    assert 'not JSON' in wf.check_top('none', DEFINITION_INPUT, n(1))['refused']


def test_top_an_unknown_subject_is_a_flow_defect():
    with pytest.raises(ValueError, match="no subject 'X-1'"):
        wf.check_top(answer(requirements=[top()]), DEFINITION_INPUT, 'X-1')


# ---- BOUNDARY ----

def boundary_item(key, parent='T-21', assumptions=None, statement='The service offers an operation that sets a desired price.'):
    item = {'key': key, 'parent': parent, 'title': 'Item ' + key, 'statement': statement, 'rationale': 'why'}
    if assumptions is not None:
        item['assumptions'] = assumptions
    return item


def test_boundary_prompt_lists_requirements_and_items():
    p = wf.compose_boundary(BOUNDARY_INPUT)
    assert 'T-21 - Publish' in p and 'T-22 - Settle' in p
    assert '- I-13 ASSUMPTION' in p and '- I-15 OPEN_CHOICE governing ' + n(4) in p
    assert 'simulates ONLY what the ASSUMPTION items state' in p


def test_boundary_check_accepts_a_valid_answer():
    out = wf.check_boundary(answer(interface=[boundary_item('IF-1')],
                                   environment=[boundary_item('EN-1', 'T-22', ['I-13', 'I-14'], 'The simulation reorders sends.')]),
                            BOUNDARY_INPUT)
    assert 'refused' not in out, out
    assert out['environment'][0]['assumptions'] == ['I-13', 'I-14']
    assert 'assumptions' not in out['interface'][0]


def test_boundary_check_refuses_by_its_rules():
    env = [boundary_item('EN-1', 'T-22', ['I-13', 'I-14'], 'The simulation reorders sends.')]
    assert 'is not a top-level requirement' in wf.check_boundary(answer(interface=[boundary_item('IF-1', 'T-99')], environment=env),
                                                                 BOUNDARY_INPUT)['refused']
    assert 'names no assumption' in wf.check_boundary(answer(interface=[boundary_item('IF-1', 'T-21', ['I-13'])], environment=env),
                                                       BOUNDARY_INPUT)['refused']
    assert 'named by no environment item' in wf.check_boundary(answer(interface=[boundary_item('IF-1')],
        environment=[boundary_item('EN-1', 'T-22', ['I-13'], 'The simulation reorders sends.')]), BOUNDARY_INPUT)['refused']
    assert 'are not ASSUMPTION items' in wf.check_boundary(answer(interface=[boundary_item('IF-1')],
        environment=[boundary_item('EN-1', 'T-22', ['I-13', 'I-14', 'I-15'], 'The simulation reorders sends.')]), BOUNDARY_INPUT)['refused']
    assert 'holds no item' in wf.check_boundary(answer(interface=[], environment=env), BOUNDARY_INPUT)['refused']
    assert 'rule 5 (language)' in wf.check_boundary(answer(interface=[boundary_item('IF-1', statement='A JUnit fixture sets a price.')],
                                                           environment=env), BOUNDARY_INPUT)['refused']


# ---- DESIGN ----

def test_design_prompt_names_the_requirement_and_the_others_read_only():
    p = wf.compose_design(DESIGN_INPUT, 'T-21')
    assert 'T-21 - Publish' in p
    assert '- T-22: Every station shall eventually hold the latest desired price.' in p
    assert '- I-12 READING governing ' + n(1) in p


def test_design_check_puts_every_item_under_the_branch():
    out = wf.check_design(answer(design=[{'key': 'D-1', 'parent': 'T-99', 'title': 'Newest only',
                                          'statement': 'The service sends only the newest desired price.', 'rationale': 'coalesce'}]),
                          DESIGN_INPUT, 'T-21')
    assert out['design'][0]['parent'] == 'T-21'


def test_design_check_refuses_empty_or_a_language_and_raises_on_an_unknown_branch():
    assert 'holds no item' in wf.check_design(answer(design=[]), DESIGN_INPUT, 'T-21')['refused']
    assert 'rule 5 (language)' in wf.check_design(answer(design=[{'key': 'D-1', 'title': 't', 'statement': 'A Rust actor sends.',
                                                                  'rationale': 'r'}]), DESIGN_INPUT, 'T-21')['refused']
    with pytest.raises(ValueError, match="no top-level requirement 'T-99'"):
        wf.check_design(answer(design=[]), DESIGN_INPUT, 'T-99')
