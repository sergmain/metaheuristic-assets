# The NEED interpretation's prompt and check (nrvv_interpretation), on r1's agreed NEEDs from tests/data/evidence-cases.json.

import json
import os

import nrvv_interpretation as wf

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'evidence-cases.json'), encoding='utf-8') as f:
    TABLE = json.load(f)


def n(i):
    return 'GASV6A3-' + str(i)


R1_TEXT = '# The Situation\n\nYou have a central service that needs to publish gas price updates to gas stations.'
NEEDS = [{'reqId': x['reqId'], 'revision': x['revision'], 'kind': x['kind'], 'title': 'T ' + x['reqId'],
          'statement': x['statement'], 'section': 0} for x in TABLE['needs']]
G = {'id': 'G', 'global': True, 'needs': [n(i) for i in range(1, 12)], 'governable': [n(1), n(4), n(8), n(9), n(10)]}
L = {'id': 'L-' + n(1), 'global': False, 'needs': [n(1), n(9)], 'governable': [n(1)]}
CONTEXT = {'stakeholder': 'pricing team', 'sections': [{'id': 0, 'text': R1_TEXT}], 'needs': NEEDS, 'sessions': [G, L]}


def item(key, kind, needs, governs, statement, *evidence):
    return {'key': key, 'kind': kind, 'needs': needs, 'governs': governs, 'title': 'Title ' + key, 'statement': statement,
            'rationale': 'Read from the NEEDs as a set.',
            'evidence': [{'source': evidence[i], 'quote': evidence[i + 1]} for i in range(0, len(evidence), 2)]}


def valid_items():
    return [
        item('G-1', 'ASSUMPTION', [n(2)], [], 'New desired prices keep arriving while earlier sends are in flight.',
             n(2), 'new desired prices arriving while earlier sends are still in flight'),
        item('G-2', 'ASSUMPTION', [n(5)], [], 'Sends can arrive at a station out of order.',
             n(5), 'sends possibly arriving at the station out of order'),
        item('G-3', 'ASSUMPTION', [n(6)], [], 'All acknowledgements come back in order.',
             n(6), 'all acknowledgements to come back in order'),
        item('G-4', 'ASSUMPTION', [n(7)], [], 'A station cannot version or deduplicate what it receives.',
             n(7), 'versioning or deduplication impossible to add on their side'),
        item('G-5', 'READING', [n(1), n(3), n(9), n(11)], [n(1)],
             'Publishing an update is met when the station ends up holding the latest desired price; a price superseded'
             ' before delivery need not be delivered.',
             n(3), 'only eventual correctness to matter', n(9), 'unnecessary updates avoided'),
        item('G-6', 'READING', [n(8), n(10)], ['*'], 'Sending and not sending have costs that are measured and reported.',
             n(8), 'the cost of sending kept low', n(10), 'the cost of not sending kept low'),
        item('G-7', 'OPEN_CHOICE', [n(3), n(4)], [n(4)],
             'How soon a station holds the latest price is not stated; requirements hold for every delay.',
             n(3), 'only eventual correctness to matter'),
    ]


def answer(items):
    return json.dumps({'items': items})


def refusal(items, session='G'):
    out = wf.checked(answer(items), CONTEXT, session)
    assert 'refused' in out, out
    return out['refused']


# ---- the prompt ----

def test_prompt_states_the_three_kinds_and_their_rules():
    p = wf.compose(CONTEXT, 'G')
    for kind in ('- ASSUMPTION:', '- READING:', '- OPEN_CHOICE:'):
        assert kind in p
    assert p.count('Never a "shall"') == 2, 'forbidden in an ASSUMPTION and an OPEN_CHOICE'
    assert 'Every NEED of kind ENVIRONMENT_FACT, SCOPE_LIMITER or COST_OBJECTIVE listed below is cited' in p
    assert 'copied\n  exactly as the NEED states them' in p
    assert 'or is ["*"] for an item that governs every obligation' in p, 'the global session may govern *'


def test_prompt_lists_the_sessions_needs_with_kinds_and_the_section_text():
    p = wf.compose(CONTEXT, 'G')
    for x in TABLE['needs']:
        assert 'NEED ' + x['reqId'] + ' (revision 1, ' + x['kind'] + ')' in p
        assert x['statement'] in p
    assert 'You have a central service that needs to publish gas price updates to gas stations.' in p


def test_prompt_of_a_local_session_lists_only_its_needs_and_no_star():
    p = wf.compose(CONTEXT, 'L-' + n(1))
    assert 'NEED ' + n(1) + ' ' in p and 'NEED ' + n(9) + ' ' in p
    assert 'NEED ' + n(5) + ' ' not in p
    assert '["*"]' not in p.split('Answer by calling')[0], 'a local session may not govern *'
    assert 'Keys are "L-' + n(1) + '-1"' in p


def test_prompt_shows_the_first_sessions_items_read_only():
    p = wf.compose(CONTEXT, 'L-' + n(1), [{'kind': 'READING', 'needs': [n(1), n(3)], 'statement': 'Publishing is met eventually.'}])
    assert 'Items an earlier session already stated - read-only' in p
    assert '- READING citing ' + n(1) + ', ' + n(3) + ': Publishing is met eventually.' in p


def test_prompt_ends_with_the_answer_instruction():
    p = wf.compose(CONTEXT, 'G')
    tail = p.splitlines()
    assert tail[-1].startswith('Print nothing')
    assert tail[-2] == wf.ANSWER_SHAPE
    assert tail[-3].startswith('Answer by calling the mh_cc_store_result tool exactly once')


# ---- the check ----

def test_check_accepts_a_valid_answer_in_canonical_form():
    out = wf.checked(answer(valid_items()), CONTEXT, 'G')
    assert 'refused' not in out, out
    assert [i['key'] for i in out['items']] == ['G-' + str(i) for i in range(1, 8)]
    assert out['items'][4]['governs'] == [n(1)]


def test_check_unwraps_one_markdown_fence():
    out = wf.checked('```json\n' + answer(valid_items()) + '\n```', CONTEXT, 'G')
    assert 'refused' not in out, out


def test_check_refuses_not_json_or_another_shape():
    assert 'not JSON' in wf.checked('the items are', CONTEXT, 'G')['refused']
    assert 'is not {"items"' in wf.checked('{"items": [], "more": 1}', CONTEXT, 'G')['refused']


def test_check_refuses_a_key_without_the_prefix_or_twice():
    items = valid_items()
    items[0]['key'] = 'X-1'
    assert "lacks the prefix 'G-'" in refusal(items)
    items = valid_items()
    items[1]['key'] = 'G-1'
    assert 'duplicate' in refusal(items)


def test_check_refuses_an_unknown_kind_or_field():
    items = valid_items()
    items[0]['kind'] = 'FACT'
    assert 'unknown kind' in refusal(items)
    items = valid_items()
    items[0]['why'] = 'because'
    assert 'unknown field' in refusal(items)


def test_check_refuses_a_need_outside_the_session():
    items = [item('L-' + n(1) + '-1', 'READING', [n(9), n(3)], [n(1)], 'Updates are sent when needed.',
                  n(9), 'unnecessary updates avoided')]
    assert 'outside the session' in refusal(items, 'L-' + n(1))


def test_check_refuses_governs_wrong_for_the_kind_or_the_session():
    items = valid_items()
    items[0]['governs'] = [n(1)]
    assert 'governs nothing' in refusal(items)
    items = valid_items()
    items[4]['governs'] = []
    assert 'names the NEEDs it governs' in refusal(items)
    items = valid_items()
    items[4]['governs'] = [n(3)]
    assert 'may not govern' in refusal(items), 'a scope limiter is not governable'
    star = [item('L-' + n(1) + '-1', 'READING', [n(9)], ['*'], 'Updates are sent when they change a held price.',
                 n(9), 'unnecessary updates avoided')]
    assert "global session's alone" in refusal(star, 'L-' + n(1))


def test_check_refuses_by_the_evidence_rules():
    items = valid_items()
    items[0]['evidence'] = [{'source': n(2), 'quote': 'new desired prices arriving while earlier sends are still pending'}]
    assert 'rule 1 (quote)' in refusal(items)
    items = valid_items()
    items[1]['statement'] = 'Every send can arrive at a station out of order.'
    assert 'rule 2 (universal word)' in refusal(items)
    items = valid_items()
    items[3]['statement'] = 'A station runs no Python code to deduplicate.'
    assert 'rule 5 (language)' in refusal(items)


def test_check_refuses_a_qualifier_no_item_cites():
    items = valid_items()
    del items[2]
    assert n(6) in refusal(items) and 'cited by no item' in refusal(items)


def test_check_an_open_choice_is_exempt_from_the_universal_word_rule():
    out = wf.checked(answer(valid_items()), CONTEXT, 'G')
    assert out['items'][6]['kind'] == 'OPEN_CHOICE' and 'every delay' in out['items'][6]['statement']


def test_check_an_unknown_session_is_an_input_defect_not_a_refusal():
    try:
        wf.checked(answer(valid_items()), CONTEXT, 'Z')
        assert False, 'an unknown session raises'
    except ValueError as e:
        assert "no session 'Z'" in str(e)
