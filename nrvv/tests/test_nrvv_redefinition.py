# Re-definition's prompts and checks (plan 045, Phase 18): nrvv_redefinition. The same fixture and rules as the
# Dispatcher's NrvvRedefinitionUtilsTest.

import json

import pytest

import nrvv_redefinition as rd

CONTEXT = {
    'snapshotId': 77,
    'needs': [
        {'reqId': 'N-1', 'revision': 2, 'title': 'Prices', 'statement': 'Stations need the latest price.', 'delta': True},
        {'reqId': 'N-2', 'revision': 1, 'title': 'Acks', 'statement': 'The team needs acks.', 'delta': False},
        {'reqId': 'N-3', 'revision': 1, 'title': 'New', 'statement': 'Something new.', 'delta': True},
        {'reqId': 'N-4', 'revision': 1, 'title': 'Held', 'statement': 'A standard.', 'delta': False},
        {'reqId': 'N-5', 'revision': 1, 'title': 'Gone', 'statement': 'Served by an obsolete one.', 'delta': True},
    ],
    'topLevel': [
        {'reqId': 'R-1', 'liveReqId': 'R-5', 'title': 'Prices', 'statement': 'The service shall publish prices.',
         'rationale': 'need: N-1 r1\nRestates N-1.', 'citations': ['N-1 r1'], 'tracedFrom': ['N-1']},
        {'reqId': 'R-2', 'liveReqId': 'R-2', 'title': 'Acks', 'statement': 'The service shall record acknowledgements.',
         'rationale': 'need: N-2 r1, N-1 r1\nRestates N-2.', 'citations': ['N-2 r1', 'N-1 r1'], 'tracedFrom': ['N-1', 'N-2']},
    ],
    'items': [
        {'reqId': 'D-1', 'liveReqId': 'D-1', 'kind': 'design', 'parents': ['R-1'], 'title': 'Queue',
         'statement': 'A queue per station.', 'rationale': 'Design.'},
        {'reqId': 'D-2', 'liveReqId': 'D-2', 'kind': 'design', 'parents': ['R-1'], 'title': 'Retry',
         'statement': 'Retry on loss.', 'rationale': 'Design below design.'},
        {'reqId': 'E-1', 'liveReqId': 'E-1', 'kind': 'environment', 'parents': ['R-2'], 'title': 'Stations',
         'statement': 'Stations ack in order.', 'rationale': 'Environment.'},
        {'reqId': 'I-1', 'liveReqId': 'I-1', 'kind': 'interface', 'parents': ['R-1'], 'title': 'publish()',
         'statement': 'publish(price) -> ack.', 'rationale': 'Interface.'},
    ],
    'delta': ['N-1', 'N-3', 'N-5'],
    'interfaceSection': 'S-I',
    'environmentSection': 'S-E',
}

TOP_VALID = {
    'topLevel': [
        {'reqId': 'R-1', 'action': 'CHANGE', 'needs': ['N-1 r2'], 'statement': 'The service shall publish within a minute.',
         'rationale': 'Restates N-1 r2.', 'title': 'ignored'},
        {'reqId': 'R-2', 'action': 'KEEP'}],
    'add': [{'key': 'A1', 'needs': ['N-3 r1', 'N-5 r1'], 'title': 'New', 'statement': 'The service shall do the new thing.',
             'rationale': 'Restates N-3 and N-5.'}],
}


def context():
    return rd.context_of(json.dumps(CONTEXT))


def top_valid():
    return rd.check_top_level(json.dumps(TOP_VALID), context())


def top(*decisions, add=None):
    return json.dumps({'topLevel': list(decisions), 'add': add or []})


KEEP_2 = {'reqId': 'R-2', 'action': 'KEEP'}


def change_1(*needs):
    return {'reqId': 'R-1', 'action': 'CHANGE', 'needs': list(needs), 'statement': 's', 'rationale': 'r'}


# ==================== inputs ====================

def test_context_of_reads_the_context():
    assert [t['reqId'] for t in context()['topLevel']] == ['R-1', 'R-2']


@pytest.mark.parametrize('raw', ['', 'not json', '[]', json.dumps({'needs': [], 'topLevel': [], 'items': []}),
                                 json.dumps({'needs': [], 'topLevel': [], 'items': [], 'delta': []}),
                                 json.dumps({'needs': [{}], 'topLevel': [{'reqId': 'R'}], 'items': [], 'delta': []})])
def test_context_of_refuses(raw):
    with pytest.raises(ValueError):
        rd.context_of(raw)


# ==================== prompts ====================

def test_top_level_prompt_names_every_requirement_the_delta_and_the_current_revisions():
    p = rd.compose_top_level(context())
    for s in ('R-1 - Prices', 'R-2 - Acks', 'cites: N-1 r1', 'N-1, N-3, N-5', 'N-1 r2 - Prices  <-- CHANGED OR NEW: cite "N-1 r2"',
              '"action": "OBSOLETE"', 'top-level requirement'):
        assert s in p, s
    assert 'obligation' not in p, 'the vocabulary is top-level requirement (plan 045 decision 2.2.21)'
    assert 'N-2 r1 - Acks\n' in p, 'a NEED outside the delta is not marked'


def test_design_prompt_lists_only_the_items_to_answer():
    p = rd.compose_design(context(), top_valid())
    assert 'R-1 (CHANGED) - Prices' in p
    assert 'now: The service shall publish within a minute.' in p
    assert 'A1 (ADDED) - New' in p
    assert 'D-1 [design] under R-1' in p and 'I-1 [interface] under R-1' in p
    assert 'E-1 [environment] Stations' in p and 'E-1 [environment] under' not in p


# ==================== the top-level answer ====================

def test_check_top_level_valid_and_canonical():
    a = top_valid()
    assert [d['action'] for d in a['topLevel']] == ['CHANGE', 'KEEP']
    assert a['topLevel'][0] == {'reqId': 'R-1', 'action': 'CHANGE', 'needs': ['N-1 r2'],
                                'statement': 'The service shall publish within a minute.'}, 'a CHANGE keeps the Rationale'
    assert a['add'][0]['needs'] == ['N-3 r1', 'N-5 r1']
    assert json.loads(rd.to_json(a)) == a


def test_check_top_level_unwraps_one_fence():
    assert rd.check_top_level('```json\n' + json.dumps(TOP_VALID) + '\n```', context())['add'][0]['key'] == 'A1'


@pytest.mark.parametrize('answer, message', [
    (top(change_1('N-1 r2', 'N-3 r1', 'N-5 r1')), 'leaves top-level requirement(s) [\'R-2\'] unnamed'),
    (top(KEEP_2, KEEP_2), 'R-2 is named twice'),
    (top({'reqId': 'R-6', 'action': 'KEEP'}), 'names R-6, which is not a top-level requirement'),
    (top({'reqId': 'R-1', 'action': 'DELETE'}), "R-1 has action 'DELETE'"),
    (top(change_1('N-1 r1'), KEEP_2), 'not the current revision of N-1 (r2)'),
    (top(change_1('N-9 r1'), KEEP_2), 'N-9 r1, which is not an agreed NEED'),
    (top(change_1(), KEEP_2), 'R-1 cites no NEED'),
    (top(change_1('N-1'), KEEP_2), 'does not read'),
    (top(change_1('N-1 r2', 'N-1 r2'), KEEP_2), 'R-1 cites N-1 twice'),
    (top(change_1('N-1 r2'), KEEP_2), "leaves delta NEED(s) ['N-3', 'N-5'] uncited"),
    (top({'reqId': 'R-1', 'action': 'OBSOLETE'}, KEEP_2), 'R-1 has no reason'),
    (top({'reqId': 'R-1', 'action': 'CHANGE', 'needs': ['N-1 r2', 'N-3 r1', 'N-5 r1'], 'statement': 'a \u00abq\u00bb',
          'rationale': 'r'}, KEEP_2), 'holds a guillemet'),
    (top({'reqId': 'R-1', 'action': 'KEEP'}, KEEP_2, add=[{'key': 'R-2', 'needs': ['N-1 r2'], 'title': 't',
                                                            'statement': 's', 'rationale': 'r'}]), 'is used twice or is an existing reqId'),
    ('[]', 'no JSON object'),
    ('{}', "'topLevel' is missing"),
])
def test_check_top_level_refusals(answer, message):
    with pytest.raises(ValueError) as e:
        rd.check_top_level(answer, context())
    assert message in str(e.value), str(e.value)


def test_check_top_level_refuses_every_obsolete_and_no_add():
    no_delta = dict(CONTEXT, delta=[])
    with pytest.raises(ValueError) as e:
        rd.check_top_level(top({'reqId': 'R-1', 'action': 'OBSOLETE', 'reason': 'x'},
                               {'reqId': 'R-2', 'action': 'OBSOLETE', 'reason': 'x'}), rd.context_of(json.dumps(no_delta)))
    assert 'obsoletes every top-level requirement and adds none' in str(e.value)


# ==================== the design answer ====================

def test_items_to_answer():
    assert rd.items_to_answer(context(), top_valid()) == ['D-1', 'D-2', 'I-1']
    obsolete_1 = rd.check_top_level(top({'reqId': 'R-1', 'action': 'OBSOLETE', 'reason': 'x'},
                                        {'reqId': 'R-2', 'action': 'CHANGE', 'needs': ['N-1 r2', 'N-2 r1', 'N-3 r1', 'N-5 r1'],
                                         'statement': 's', 'rationale': 'r'}), context())
    assert rd.items_to_answer(context(), obsolete_1) == ['E-1']


def design(items, add=None):
    return json.dumps({'items': items, 'add': add or []})


K = lambda r: {'reqId': r, 'action': 'KEEP'}


def test_check_design_valid():
    d = rd.check_design(design([K('D-1'), {'reqId': 'D-2', 'action': 'OBSOLETE', 'reason': 'no retry'},
                                {'reqId': 'I-1', 'action': 'CHANGE', 'statement': 's', 'rationale': 'r'}],
                               [{'key': 'D1', 'parent': 'R-1', 'title': 't', 'statement': 's', 'rationale': 'r'},
                                {'key': 'E1', 'parent': 'A1', 'title': 't', 'statement': 's', 'rationale': 'r'}]),
                        context(), top_valid())
    assert [x['action'] for x in d['items']] == ['KEEP', 'OBSOLETE', 'CHANGE']
    assert [a['parent'] for a in d['add']] == ['R-1', 'A1']


@pytest.mark.parametrize('answer, message', [
    (design([K('D-1'), K('D-2')]), "leaves item(s) ['I-1'] unnamed"),
    (design([K('D-1'), K('D-2'), K('I-1'), K('E-1')]), 'names E-1, which is under no CHANGED top-level requirement'),
    (design([K('D-1'), K('D-1')]), 'item D-1 is named twice'),
    (design([K('D-1'), K('D-2'), K('I-1')], [{'key': 'D1', 'parent': 'R-2', 'title': 't', 'statement': 's', 'rationale': 'r'}]),
     "D1 names parent 'R-2'"),
    (design([K('D-1'), K('D-2'), K('I-1')], [{'key': 'X1', 'parent': 'R-1', 'title': 't', 'statement': 's', 'rationale': 'r'}]),
     'the add key X1 does not start with D, I or E'),
    (design([K('D-1'), K('D-2'), {'reqId': 'I-1', 'action': 'OBSOLETE', 'reason': 'x'}]),
     'after this answer 0 Interface and 1 Environment item(s) remain'),
    (design([{'reqId': 'D-1', 'action': 'CHANGE', 'statement': 's'}, K('D-2'), K('I-1')]), 'D-1 has no rationale'),
])
def test_check_design_refusals(answer, message):
    with pytest.raises(ValueError) as e:
        rd.check_design(answer, context(), top_valid())
    assert message in str(e.value), str(e.value)


def test_check_design_an_item_under_an_obsolete_top_level_is_not_named():
    obsolete_1 = rd.check_top_level(top({'reqId': 'R-1', 'action': 'OBSOLETE', 'reason': 'x'},
                                        {'reqId': 'R-2', 'action': 'CHANGE', 'needs': ['N-1 r2', 'N-2 r1', 'N-3 r1', 'N-5 r1'],
                                         'statement': 's', 'rationale': 'r'}), context())
    with pytest.raises(ValueError) as e:
        rd.check_design(design([K('E-1'), K('I-1')]), context(), obsolete_1)
    assert 'names I-1, which goes OBSOLETE with its top-level requirement' in str(e.value)
    with pytest.raises(ValueError) as e:
        rd.check_design(design([K('E-1')]), context(), obsolete_1)
    assert '0 Interface and 1 Environment' in str(e.value)
    ok = rd.check_design(design([K('E-1')], [{'key': 'I1', 'parent': 'R-2', 'title': 't', 'statement': 's', 'rationale': 'r'}]),
                         context(), obsolete_1)
    assert len(ok['add']) == 1


def test_top_level_of_reads_a_checked_answer():
    assert rd.top_level_of(rd.to_json(top_valid()))['topLevel'][1] == {'reqId': 'R-2', 'action': 'KEEP'}
    with pytest.raises(ValueError):
        rd.top_level_of(json.dumps({'topLevel': []}))


def test_check_top_level_a_change_needs_a_citation_line_to_re_cite():
    uncited = dict(CONTEXT, topLevel=[dict(CONTEXT['topLevel'][0], rationale='linked by hand'), CONTEXT['topLevel'][1]])
    with pytest.raises(ValueError) as e:
        rd.check_top_level(json.dumps(TOP_VALID), rd.context_of(json.dumps(uncited)))
    assert 'R-1 has no citation line' in str(e.value)


def test_check_design_a_change_rewords_the_first_paragraph_of_the_rationale():
    d = rd.check_design(design([{'reqId': 'D-1', 'action': 'CHANGE', 'statement': 's', 'rationale': 'two\nlines'},
                                K('D-2'), K('I-1')]), context(), top_valid())
    assert d['items'][0]['rationale'] == 'two lines'
    with pytest.raises(ValueError) as e:
        rd.check_design(design([{'reqId': 'D-1', 'action': 'CHANGE', 'statement': 's', 'rationale': 'a "quoted" word'},
                                K('D-2'), K('I-1')]), context(), top_valid())
    assert "D-1's rationale holds a double quote" in str(e.value)
    quoted = dict(CONTEXT, items=[dict(CONTEXT['items'][0], rationale='a "quoted" Rationale')] + CONTEXT['items'][1:])
    with pytest.raises(ValueError) as e:
        rd.check_design(design([{'reqId': 'D-1', 'action': 'CHANGE', 'statement': 's', 'rationale': 'r'}, K('D-2'), K('I-1')]),
                        rd.context_of(json.dumps(quoted)), top_valid())
    assert "item D-1's Rationale holds a double quote" in str(e.value)


def test_citation_line_of_and_first_paragraph():
    assert rd.citation_line_of('why\n  need: N-1 r1 \nmore') == 'need: N-1 r1'
    assert rd.citation_line_of('none') is None
    assert rd.first_paragraph('\n first \nsecond') == 'first'
    assert rd.first_paragraph('') == ''
