# BACKTRACE over interpretation items (nrvv_cv_need_backtrace): an item is judged by its kind, a requirement together
# with the items it is read under and its evidence. Characterization test: Green-1 pins the prompt as it is, Red flips
# the assertions to the kind-aware prompt, Green-3 changes the payload.

import nrvv_cv_need_backtrace as backtrace

NEEDS = [
    {'reqId': 'GAS-1', 'revision': 1, 'title': 'Publish', 'kind': 'OBLIGATION',
     'statement': 'The pricing team needs the central service to publish gas price updates to gas stations.'},
    {'reqId': 'GAS-5', 'revision': 1, 'title': 'Out of order', 'kind': 'ENVIRONMENT_FACT',
     'statement': 'The pricing team needs to account for sends possibly arriving at the station out of order.'},
]


def subject(req_id, statement, rationale, kind=None, governs=(), readings=(), evidence=()):
    return {'reqId': req_id, 'liveReqId': req_id, 'held': False, 'sectionReqId': None, 'title': 'T ' + req_id,
            'statement': statement, 'rationale': rationale, 'citations': [], 'superseded': [], 'tracedFrom': ['GAS-1'],
            'interpretationKind': kind, 'governs': list(governs), 'readings': list(readings),
            'evidence': [{'source': evidence[i], 'quote': evidence[i + 1]} for i in range(0, len(evidence), 2)]}


ASSUMPTION = subject('GAS-30', 'Sends can arrive at a station out of order.',
                     'need: GAS-5 r1\ninterpretation: ASSUMPTION\nevidence: GAS-5 "arriving at the station out of order"',
                     kind='ASSUMPTION', evidence=('GAS-5', 'arriving at the station out of order'))
READING = subject('GAS-31', 'Publishing an update is met when the station ends up holding the latest desired price.',
                  'need: GAS-1 r1\ninterpretation: READING\ngoverns: GAS-1\nevidence: GAS-1 "publish gas price updates"',
                  kind='READING', governs=('GAS-1',), evidence=('GAS-1', 'publish gas price updates'))
REQUIREMENT = subject('GAS-40', 'The service shall send a station the latest desired price until the station acknowledges it.',
                      'need: GAS-1 r1\nreading: GAS-31\nevidence: GAS-1 "publish gas price updates"',
                      readings=({'reqId': 'GAS-31', 'kind': 'READING', 'statement': READING['statement']},),
                      evidence=('GAS-1', 'publish gas price updates'))
CONTEXT = {'snapshotId': 7, 'needs': NEEDS, 'subjects': [ASSUMPTION, READING, REQUIREMENT]}
CHUNK = ['GAS-30', 'GAS-31', 'GAS-40']


def test_prompt_judges_an_interpretation_item_by_its_kind():
    p = backtrace.compose(CONTEXT, CHUNK)
    assert 'Interpretation item GAS-30 (ASSUMPTION - JUSTIFIED, OVER_REACH, CONTRADICTS_NEED or RESTS_ON_SUPERSEDED):' in p
    assert 'Interpretation item GAS-31 (READING - JUSTIFIED, OVER_REACH, CONTRADICTS_NEED or RESTS_ON_SUPERSEDED):' in p
    assert 'Owned requirement GAS-30 ' not in p and 'Owned requirement GAS-31 ' not in p
    assert '    Governs: GAS-1' in p
    assert '- An interpretation item is judged by its kind.' in p
    assert ('An ASSUMPTION is JUSTIFIED when a NEED it cites states the fact it states, and OVER_REACH when it assumes'
            ' more than the NEEDs state') in p
    assert ('A READING or an OPEN_CHOICE is OVER_REACH when it adds an obligation no NEED states or narrows what the NEEDs'
            ' allow') in p


def test_prompt_judges_a_requirement_with_its_readings_and_evidence():
    p = backtrace.compose(CONTEXT, CHUNK)
    assert 'Owned requirement GAS-40 (top-level - JUSTIFIED, OVER_REACH, CONTRADICTS_NEED or RESTS_ON_SUPERSEDED):' in p
    assert '    Read under: READING GAS-31: ' + READING['statement'] in p
    assert '    Evidence: GAS-1 "publish gas price updates"' in p
    assert '    Evidence: GAS-5 "arriving at the station out of order"' in p
    assert '- A requirement is judged together with the items it is read under and its evidence quotes' in p


def test_a_v6_context_renders_as_before():
    v6 = {k: v for k, v in REQUIREMENT.items() if k not in ('interpretationKind', 'governs', 'readings', 'evidence')}
    p = backtrace.compose({'snapshotId': 7, 'needs': NEEDS, 'subjects': [v6]}, ['GAS-40'])
    assert 'Owned requirement GAS-40 (top-level' in p
    assert 'Read under:' not in p and 'Evidence:' not in p and 'Governs:' not in p
