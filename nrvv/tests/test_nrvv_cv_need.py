# The NEED checks of NRVV v5 (plan 047, Phase 10): the CONTRADICTION and QUALITY prompts - their tails and what they
# list - and every refusal of the shared check, the mirrored pair stored once.

import json

import pytest

import nrvv_cv_need as cv
import nrvv_cv_need_backtrace as backtrace
import nrvv_cv_need_contradiction as contradiction
import nrvv_cv_need_feasibility as feasibility
import nrvv_cv_need_quality as quality

NEEDS = [
    {'reqId': 'GAS-2', 'revision': 1, 'title': 'Settle', 'statement': 'The pricing team needs each station to settle\non the latest price.',
     'parentReqId': None, 'kind': 'OBLIGATION'},
    {'reqId': 'GAS-6', 'revision': 1, 'title': 'Keep first', 'statement': 'The pricing team needs each station to keep the first price.',
     'parentReqId': None, 'kind': 'OBLIGATION'},
    {'reqId': 'GAS-7', 'revision': 1, 'title': 'Costs', 'statement': 'Sending has a cost.', 'parentReqId': None,
     'kind': 'COST_OBJECTIVE'},
    {'reqId': 'GAS-9', 'revision': 1, 'title': 'v4 NEED', 'statement': 'No kind line.', 'parentReqId': None},
]


def answer(*findings):
    return json.dumps({'findings': list(findings)})


def finding(kind, subject, counterpart=None, text='what is wrong'):
    f = {'kind': kind, 'subject': subject, 'text': text}
    if counterpart is not None:
        f['counterpart'] = counterpart
    return f


# ==================== prompts ====================

@pytest.mark.parametrize('module', [contradiction, quality])
def test_prompt_ends_with_the_answer_instruction(module):
    lines = module.compose(NEEDS).split('\n')
    assert lines[-1] == cv.ANSWER_TAIL
    assert lines[-2] == cv.ANSWER_SHAPE
    assert lines[-3].startswith('Answer by calling the mh_cc_store_result tool exactly once')
    assert 'Print nothing' in lines[-1]


@pytest.mark.parametrize('module', [contradiction, quality])
def test_prompt_lists_every_need_with_its_kind(module):
    prompt = module.compose(NEEDS)
    assert 'NEED GAS-2 (OBLIGATION): Settle' in prompt
    assert '  on the latest price.' in prompt, 'a multi-line statement keeps its lines'
    assert 'NEED GAS-7 (COST_OBJECTIVE): Costs' in prompt
    assert 'NEED GAS-9: v4 NEED' in prompt, 'a NEED without a kind is listed without one'
    assert 'A NEED without a kind is an OBLIGATION.' in prompt
    assert prompt.index('NEED GAS-9') < prompt.index('mh_cc_store_result'), 'the instruction is LAST'


def test_prompt_without_needs():
    assert 'The project has no agreed NEED.' in contradiction.compose([])


def test_contradiction_prompt_asks_for_the_minimal_witness_and_spares_costs():
    prompt = contradiction.compose(NEEDS)
    assert 'minimal witness situation' in prompt
    assert 'COST_OBJECTIVE NEED against any other NEED' in prompt
    assert 'No finding at all is a valid answer' in prompt


def test_quality_prompt_names_its_five_kinds_and_leaves_contradictions_out():
    prompt = quality.compose(NEEDS)
    for kind in quality.KINDS:
        assert '- ' + kind + ':' in prompt, kind
    assert 'cannot both hold are not a quality matter' in prompt


# ==================== check ====================

def test_contradiction_check_keeps_one_of_a_mirrored_pair():
    out = cv.findings_of(answer(finding('CONTRADICTION', 'GAS-6', 'GAS-2', 'first'), finding('CONTRADICTION', 'GAS-2', 'GAS-6', 'mirror')),
                         NEEDS, contradiction.KINDS, contradiction.PAIR_KINDS)['findings']
    assert out == [{'kind': 'CONTRADICTION', 'subject': 'GAS-6', 'counterpart': 'GAS-2', 'text': 'first'}]


def test_check_unwraps_one_fence_and_accepts_no_finding():
    assert cv.findings_of('```json\n{"findings": []}\n```', NEEDS, contradiction.KINDS, contradiction.PAIR_KINDS) == {'findings': []}


def test_quality_check_single_need_kinds_and_a_redundancy():
    out = cv.findings_of(answer(finding('VAGUE_TERM', 'GAS-2', text='"settle" is not checkable'),
                                finding('VAGUE_TERM', 'GAS-2', text='repeated'),
                                finding('REDUNDANCY', 'GAS-2', 'GAS-6')),
                         NEEDS, quality.KINDS, quality.PAIR_KINDS)['findings']
    assert [(f['kind'], f['subject'], f.get('counterpart')) for f in out] == [('VAGUE_TERM', 'GAS-2', None),
                                                                              ('REDUNDANCY', 'GAS-2', 'GAS-6')]
    assert out[0]['text'] == '"settle" is not checkable', 'the first of a repeated finding is kept'


@pytest.mark.parametrize('raw, module, message', [
    ('not json', contradiction, 'not JSON'),
    (json.dumps({'clauses': []}), contradiction, 'no {"findings"'),
    (answer(finding('VAGUE_TERM', 'GAS-2')), contradiction, 'does not report'),
    (answer(finding('CONTRADICTION', 'GAS-2', 'GAS-6')), quality, 'does not report'),
    (answer(finding('GAP', 'GAS-2')), quality, 'does not report'),
    (answer(dict(finding('CONTRADICTION', 'GAS-2', 'GAS-6'), witness='x')), contradiction, 'unknown field'),
    (answer(finding('CONTRADICTION', 'GAS-2', 'GAS-6', text=' ')), contradiction, 'no text'),
    (answer(finding('CONTRADICTION', 'GAS-99', 'GAS-6')), contradiction, 'not one of the agreed NEEDs'),
    (answer(finding('CONTRADICTION', 'GAS-2')), contradiction, 'names no other agreed NEED'),
    (answer(finding('CONTRADICTION', 'GAS-2', 'GAS-2')), contradiction, 'names no other agreed NEED'),
    (answer(finding('REDUNDANCY', 'GAS-2')), quality, 'names no other agreed NEED'),
    (answer(finding('VAGUE_TERM', 'GAS-2', 'GAS-99')), quality, 'not another agreed NEED'),
])
def test_check_refuses(raw, module, message):
    with pytest.raises(ValueError) as e:
        cv.findings_of(raw, NEEDS, module.KINDS, module.PAIR_KINDS)
    assert message in str(e.value)


def test_conflict_key():
    assert cv.conflict_key('CONTRADICTION', 'GAS-6', 'GAS-2', ('CONTRADICTION',)) == 'CONTRADICTION|GAS-2|GAS-6'
    assert cv.conflict_key('VAGUE_TERM', 'GAS-6', None, ('REDUNDANCY',)) == 'VAGUE_TERM|GAS-6'
    assert cv.conflict_key('VAGUE_TERM', 'GAS-6', 'GAS-2', ('REDUNDANCY',)) == 'VAGUE_TERM|GAS-6'


# ==================== FEASIBILITY (plan 047, Phase 11) ====================

WITNESS = ('One publisher per station keeps the newest price and resends it until acknowledged: GAS-2 holds by resending '
           'the newest; GAS-6 is met by never replacing the first; GAS-7 by coalescing; GAS-9 by default.')


def test_feasibility_prompt_tail_and_verdicts():
    prompt = feasibility.compose(NEEDS)
    lines = prompt.split('\n')
    assert lines[-1].startswith('Print nothing')
    assert lines[-2] == feasibility.ANSWER_SHAPE
    assert 'mh_cc_store_result' in lines[-4] or 'mh_cc_store_result' in lines[-3]
    for v in feasibility.VERDICTS:
        assert '- ' + v + ':' in prompt, v
    assert 'MINIMAL set' in prompt
    assert 'names EVERY agreed NEED' in prompt
    assert 'Optimality is not a criterion' in prompt
    assert prompt.index('NEED GAS-9') < prompt.index('mh_cc_store_result'), 'the instruction is LAST'


def test_feasibility_infeasible_canonical():
    raw = json.dumps({'verdict': 'INFEASIBLE', 'needReqIds': [' GAS-6', 'GAS-2'], 'reason': ' keep first vs latest ',
                      'witness': None, 'openChoices': []})
    assert feasibility.verdict_of(raw, NEEDS) == {'verdict': 'INFEASIBLE', 'needReqIds': ['GAS-6', 'GAS-2'],
                                                  'reason': 'keep first vs latest'}


def test_feasibility_underdetermined_and_determined_canonical():
    out = feasibility.verdict_of(json.dumps({'verdict': 'UNDERDETERMINED', 'witness': WITNESS,
                                             'openChoices': ['the resend interval']}), NEEDS)
    assert out == {'verdict': 'UNDERDETERMINED', 'witness': WITNESS, 'openChoices': ['the resend interval']}
    out = feasibility.verdict_of(json.dumps({'verdict': 'DETERMINED', 'witness': WITNESS, 'needReqIds': []}), NEEDS)
    assert out == {'verdict': 'DETERMINED', 'witness': WITNESS}


def test_feasibility_witness_names_need_by_reqid_not_by_prefix():
    assert feasibility.names('meets GAS-2 and GAS-21', 'GAS-2')
    assert not feasibility.names('meets GAS-21 only', 'GAS-2')


# plan 050 Phase 17: a stronger model groups NEEDs in its witness - GASV8A15-4/3, GASV8A15-5/7 (#116; #113 the same) - and
# names every one; the check refused 8 of 13 sonnet attempts for it and #116's FEASIBILITY group stayed incomplete
GROUPED = ('One publisher per station keeps the newest price and resends it until acknowledged: GAS-2 holds by resending '
           'the newest; GAS-6/7 are met by never replacing the first and by coalescing; GAS-9 by default.')


def test_feasibility_witness_naming_needs_in_a_slash_group():
    out = feasibility.verdict_of(json.dumps({'verdict': 'DETERMINED', 'witness': GROUPED}), NEEDS)
    assert out == {'verdict': 'DETERMINED', 'witness': GROUPED.replace('GAS-6/7', 'GAS-6/GAS-7')}


# plan 053 (characterization test): X1 E1 #123 GASV8X1E1 on CC - every FEASIBILITY attempt (5 of 5) refused, the group
# incomplete, the project ended at its NEED gate: the witness joined NEEDs as "GASV8X1E1-4 and -3", "-5 and -7", "-8 and
# -9", naming each; expand_groups knew only the slash form "GAS-6/7". The observed answer (Variable 222306) byte for byte.
PAIRED = ('One publisher per station keeps the newest price and resends it until acknowledged: GAS-2 and -6 hold by '
          'resending the newest and never replacing the first; GAS-7 & -9 by coalescing and by default.')
E1_NEEDS = [{'reqId': 'GASV8X1E1-' + str(n), 'revision': 1, 'title': 'T' + str(n), 'statement': 'S' + str(n),
             'parentReqId': None, 'kind': 'OBLIGATION'} for n in range(1, 11)]
E1_ANSWER = ('{"verdict":"UNDERDETERMINED","needReqIds":[],"reason":"","witness":"Central service keeps per-station state: '
             'desired (latest price), lastAcked, inFlight flag. Stop-and-wait with coalescing. GASV8X1E1-1: the service publishes '
             'price updates to stations. GASV8X1E1-2: new prices only overwrite the station\'s desired value while a send is in '
             'flight; they never queue. GASV8X1E1-5 and -7: because at most one send per station is outstanding, nothing can '
             'be reordered at the dumb station, so no station-side versioning or dedup is needed. GASV8X1E1-6: the in-order ack '
             'for the single outstanding send releases the next one. On ack, if desired != acked, send desired once; otherwise '
             'send nothing. GASV8X1E1-4 and -3: when input stops, the last send carries the latest price, so each station '
             'settles on it. Intermediate states may be stale or skipped. GASV8X1E1-8 and -9: superseded intermediate prices are '
             'never sent, and unchanged prices are not resent, which avoids spam and unnecessary updates. GASV8X1E1-10: the next '
             'send goes out as soon as the ack arrives, which keeps staleness low.","openChoices":["Ack timeout and retry '
             'policy when an ack is lost or delayed","Whether to add a debounce or minimum interval between sends to a station '
             '(trades staleness against spam)","Whether sends to different stations are independent or rate-limited globally",'
             '"How long to wait before declaring a station unreachable"]}')


def test_feasibility_witness_naming_needs_joined_by_and():
    # CT Green-1: refused - 'the witness does not name NEED GAS-6' / '... GASV8X1E1-3'
    # CT Red: "X-4 and -3", "X-7 & -9" (also "X-1, -2") name both NEEDs - written in full, as the slash form is
    out = feasibility.verdict_of(json.dumps({'verdict': 'DETERMINED', 'witness': PAIRED}), NEEDS)
    assert out == {'verdict': 'DETERMINED',
                   'witness': PAIRED.replace('GAS-2 and -6', 'GAS-2 and GAS-6').replace('GAS-7 & -9', 'GAS-7 & GAS-9')}
    e1 = feasibility.verdict_of(E1_ANSWER, E1_NEEDS)
    assert e1['verdict'] == 'UNDERDETERMINED' and len(e1['openChoices']) == 4, e1
    for pair in ('GASV8X1E1-5 and GASV8X1E1-7', 'GASV8X1E1-4 and GASV8X1E1-3', 'GASV8X1E1-8 and GASV8X1E1-9'):
        assert pair in e1['witness'], pair
    assert 'GASV8X1E1-1, GASV8X1E1-2' in feasibility.expand_groups('GASV8X1E1-1, -2 hold', [n['reqId'] for n in E1_NEEDS])


# plan 053 (characterization test): X1 C2R #133 GASV8X1C2R on CC, payload 14250c8 - FEASIBILITY runs #3907, #3910, #4010
# refused 'the witness does not name NEED GASV8X1C2R-2': the witness writes the prefix once (GASV8X1C2R-1) and every other
# NEED as a bare suffix opening its own sentence - "-2:", "-5:", "-3/-4:" - naming each of the nine. The observed answer
# (Variable 230701) byte for byte.
C2R_NEEDS = [{'reqId': 'GASV8X1C2R-' + str(n), 'revision': 1, 'title': 'T' + str(n), 'statement': 'S' + str(n),
              'parentReqId': None, 'kind': 'OBLIGATION'} for n in range(1, 10)]
C2R_ANSWER = ('{"verdict": "UNDERDETERMINED", "needReqIds": [], "reason": "", "witness": "Central service keeps per-station '
              'desired price (latest) and last-acked price, and allows at most ONE send in flight per station. GASV8X1C2R-1: '
              'the service publishes prices to stations. -2: new prices just overwrite the station\'s desired value while a '
              'send is in flight; nothing is queued. -5: with one send in flight per station, no two sends can race, so '
              'reordering cannot occur. -6: acks are in order, so each ack maps to its send. -7: no station-side versioning '
              'or dedup; all ordering is enforced centrally. -3/-4: when an ack arrives, if desired differs from acked, send '
              'the latest desired; once updates stop, the last send carries the latest price, so the station settles on it. '
              '-8: intermediate prices superseded during flight are never sent (coalescing), and no send happens when desired '
              'equals acked. -9: a new send goes out as soon as the previous ack returns, which bounds how long a station '
              'stays stale to about one round trip.", "openChoices": ["Ack-timeout and retry policy for lost sends or acks", '
              '"Whether to add a minimum interval or debounce between sends to the same station, trading send cost against '
              'staleness", "Whether a station may have a send in flight to different stations concurrently, and any global '
              'rate limit", "How the service learns a station\'s initial or current price after restart (resend all or '
              'query)"]}')


def test_feasibility_witness_naming_needs_by_a_bare_suffix():
    # CT Green-1: refused - 'the witness does not name NEED GASV8X1C2R-2'
    # CT Red: a bare suffix ("-2:", "-3/-4:") names the NEED of the one prefix the witness names - written in full
    out = feasibility.verdict_of(C2R_ANSWER, C2R_NEEDS)
    assert out['verdict'] == 'UNDERDETERMINED' and len(out['openChoices']) == 4, out
    for named in ('GASV8X1C2R-1:', 'GASV8X1C2R-2:', 'GASV8X1C2R-5:', 'GASV8X1C2R-3/GASV8X1C2R-4:', 'GASV8X1C2R-9:'):
        assert named in out['witness'], named
    assert 'per-station' in out['witness'] and 'last-acked' in out['witness'], 'a hyphen inside a word names nothing'
    known = [n['reqId'] for n in C2R_NEEDS]
    assert feasibility.expand_groups('-2: holds', known) == '-2: holds', 'no prefix named - nothing to expand'
    assert feasibility.expand_groups('GASV8X1C2R-1 holds; -12 does not', known) == 'GASV8X1C2R-1 holds; -12 does not', \
        'a suffix no agreed NEED carries is left as it is'
    assert feasibility.expand_groups('GAS-1 and X-1; -2 holds', ['GAS-1', 'GAS-2', 'X-1', 'X-2']) == \
        'GAS-1 and X-1; -2 holds', 'two prefixes named - a bare suffix is ambiguous'


# plan 053 (characterization test): X1 C2R2 #136 GASV8X1C2R2 on CC, payload 3ded886 - FEASIBILITY runs #4066 / #4067 (and
# #133's #4023 before them) refused 'the witness does not name NEED GASV8X1C2R2-1': the witness numbers its points by the
# NEEDs' suffixes in brackets - "[1]" ... "[9]" - and writes no reqId at all. The observed answer (Variable 233795) byte for
# byte.
C2R2_NEEDS = [{'reqId': 'GASV8X1C2R2-' + str(n), 'revision': 1, 'title': 'T' + str(n), 'statement': 'S' + str(n),
               'parentReqId': None, 'kind': 'OBLIGATION'} for n in range(1, 10)]
C2R2_ANSWER = ('{"verdict":"UNDERDETERMINED","needReqIds":[],"reason":"","witness":"Central publisher keeps per-station '
               'state: desiredPrice (latest) and lastAcked. Strictly one send in flight per station. [1] The central service '
               'publishes price updates to stations. [2] New prices arriving mid-send just overwrite desiredPrice (coalescing); '
               'they never start a parallel send. [3] Only eventual correctness: no ordering or latency guarantee for '
               'intermediate states. [4] When the in-flight send is acked, if desiredPrice != lastAcked, send desiredPrice; so '
               'each station converges to the latest price. Unacked sends are retried after a timeout. [5] Out-of-order arrival '
               'is harmless because at most one send per station is outstanding, so nothing can overtake it. [6] In-order acks '
               'match the single outstanding send one-to-one, so an ack is unambiguous. [7] The design needs no station-side '
               'versioning or dedup; sends are idempotent full-price sets and all ordering logic is central. [8] Coalescing '
               'drops superseded intermediate prices and skips sends when desired equals acked, so there is no spam or '
               'unnecessary update. [9] Sending immediately after each ack keeps the stale window short.","openChoices":'
               '["Retry timeout and backoff for unacked sends","Whether to add a minimum delay or batching window between sends, '
               'trading sending cost against staleness","Whether stations are sent to in parallel or throttled globally",'
               '"Whether a send in flight is allowed to be superseded early, or must always be waited for"]}')


def test_feasibility_witness_naming_needs_by_a_bracketed_suffix():
    # CT Green-1: refused - 'the witness does not name NEED GASV8X1C2R2-1'
    # CT Red: "[N]" names the NEED of the agreed NEEDs' one prefix - written in full inside the brackets
    out = feasibility.verdict_of(C2R2_ANSWER, C2R2_NEEDS)
    assert out['verdict'] == 'UNDERDETERMINED' and len(out['openChoices']) == 4, out
    for named in ('[GASV8X1C2R2-1] The central', '[GASV8X1C2R2-4] When', '[GASV8X1C2R2-9] Sending'):
        assert named in out['witness'], named
    known = [n['reqId'] for n in C2R2_NEEDS]
    assert feasibility.expand_groups('[12] holds', known) == '[12] holds', 'a number no agreed NEED carries'
    assert feasibility.expand_groups('[1] holds', ['GAS-1', 'X-1']) == '[1] holds', 'two prefixes - ambiguous'
    assert feasibility.expand_groups('-2: holds', known) == '-2: holds', 'a bare suffix still needs its prefix named'


@pytest.mark.parametrize('answer_object, message', [
    ({'verdict': 'MAYBE', 'witness': WITNESS}, 'unknown verdict'),
    ({'verdict': 'DETERMINED', 'witness': WITNESS, 'design': 'x'}, 'unknown field'),
    ({'verdict': 'INFEASIBLE', 'needReqIds': [], 'reason': 'r'}, 'at least one NEED'),
    ({'verdict': 'INFEASIBLE', 'reason': 'r'}, 'at least one NEED'),
    ({'verdict': 'INFEASIBLE', 'needReqIds': ['GAS-99'], 'reason': 'r'}, 'not one of the agreed NEEDs'),
    ({'verdict': 'INFEASIBLE', 'needReqIds': ['GAS-2', 'GAS-2'], 'reason': 'r'}, 'twice'),
    ({'verdict': 'INFEASIBLE', 'needReqIds': ['GAS-2'], 'reason': ' '}, 'reason'),
    ({'verdict': 'DETERMINED'}, 'witness design'),
    ({'verdict': 'DETERMINED', 'witness': WITNESS.replace('GAS-9', 'the last')}, 'does not name NEED GAS-9'),
    ({'verdict': 'DETERMINED', 'witness': WITNESS + 'x' * 2000}, 'at most 2000'),
    ({'verdict': 'UNDERDETERMINED', 'witness': WITNESS}, 'leave open'),
    ({'verdict': 'UNDERDETERMINED', 'witness': WITNESS, 'openChoices': [' ']}, 'leave open'),
])
def test_feasibility_check_refuses(answer_object, message):
    with pytest.raises(ValueError) as e:
        feasibility.verdict_of(json.dumps(answer_object), NEEDS)
    assert message in str(e.value)


def test_feasibility_check_refuses_a_non_object():
    with pytest.raises(ValueError) as e:
        feasibility.verdict_of('["DETERMINED"]', NEEDS)
    assert 'no {"verdict"' in str(e.value)


# ==================== BACKTRACE (plan 047, Phase 17) ====================

BT_CONTEXT = {
    'snapshotId': 249,
    'needs': [
        {'reqId': 'GAS-2', 'revision': 2, 'title': 'Settle within a minute',
         'statement': 'Each station must settle on the latest price,\nand the pricing team knows within one minute.',
         'kind': 'OBLIGATION'},
        {'reqId': 'GAS-7', 'revision': 1, 'title': 'Costs', 'statement': 'Sending has a cost.', 'kind': 'COST_OBJECTIVE'},
    ],
    'subjects': [
        {'reqId': 'GAS-10', 'liveReqId': 'GAS-10', 'held': False, 'sectionReqId': None, 'title': 'Latest price',
         'statement': 'The service shall make every station display the latest price.',
         'rationale': 'need: GAS-2 r1\nrestates GAS-2', 'citations': ['GAS-2 r1'],
         'superseded': [{'needReqId': 'GAS-2', 'revision': 1, 'title': 'Settle',
                         'statement': 'Each station must settle on the latest price.'}],
         'tracedFrom': ['GAS-2']},
        {'reqId': 'GAS-11', 'liveReqId': 'GAS-14', 'held': False, 'sectionReqId': None, 'title': 'Resend spacing',
         'statement': 'The service shall send a price at most once every 60 seconds.', 'rationale': '',
         'citations': [], 'superseded': [], 'tracedFrom': []},
        {'reqId': 'GAS-12', 'liveReqId': 'GAS-12', 'held': False, 'sectionReqId': None, 'title': 'Old cite',
         'statement': 'The service shall log every send.', 'rationale': 'need: GAS-3 r1', 'citations': ['GAS-3 r1'],
         'superseded': [{'needReqId': 'GAS-3', 'revision': 1, 'title': None, 'statement': None}], 'tracedFrom': []},
        {'reqId': 'GAS-20', 'liveReqId': 'GAS-20', 'held': True, 'sectionReqId': 'GAS-19', 'title': 'Periodic resend',
         'statement': 'The service shall resend the latest price to every station every 10 seconds.', 'rationale': '',
         'citations': [], 'superseded': [], 'tracedFrom': ['GAS-7']},
    ],
}
BT_CHUNK = ['GAS-10', 'GAS-11', 'GAS-20']


def bt_verdict(subject, verdict, text='why', **fields):
    v = {'subject': subject, 'verdict': verdict, 'text': text}
    v.update(fields)
    return v


def bt_answer(*verdicts):
    return json.dumps({'verdicts': list(verdicts)})


def test_backtrace_prompt_ends_with_the_answer_instruction():
    lines = backtrace.compose(BT_CONTEXT, BT_CHUNK).split('\n')
    assert lines[-1] == cv.ANSWER_TAIL.replace('the findings', 'the verdicts')
    assert lines[-2] == backtrace.ANSWER_SHAPE
    assert lines[-4].startswith('Answer by calling the mh_cc_store_result tool exactly once')
    assert 'Print nothing' in lines[-1]


def test_backtrace_prompt_lists_the_needs_and_the_chunk_only():
    prompt = backtrace.compose(BT_CONTEXT, BT_CHUNK)
    assert 'NEED GAS-2 (revision 2, OBLIGATION): Settle within a minute' in prompt
    assert '  and the pricing team knows within one minute.' in prompt, 'a multi-line statement keeps its lines'
    assert 'NEED GAS-7 (revision 1, COST_OBJECTIVE): Costs' in prompt
    assert 'Owned requirement GAS-10 (top-level - JUSTIFIED, OVER_REACH, CONTRADICTS_NEED or RESTS_ON_SUPERSEDED):' in prompt
    assert 'Owned requirement GAS-11 (now GAS-14)' in prompt, 'a lineage read at its live row says so'
    assert 'Held requirement GAS-20 (imposed through section GAS-19 - JUSTIFIED, CONTRADICTS_NEED or UNNEEDED):' in prompt
    assert '    Rationale: need: GAS-2 r1 | restates GAS-2' in prompt
    assert '    Cites GAS-2 r1, no longer in force - it read then: Settle: Each station must settle on the latest price.' in prompt
    assert '    Traced from: no NEED' in prompt
    assert '    Traced from: GAS-7' in prompt
    assert 'GAS-12' not in prompt, 'a subject of another chunk is not listed'
    assert prompt.index('Held requirement GAS-20') < prompt.index('mh_cc_store_result'), 'the instruction is LAST'
    for rule in ('OVER_REACH (owned requirements only)', 'UNNEEDED (held requirements only)',
                 'a fixed bound on that cost', 'it obliges nothing', 'A NEED without a kind is an OBLIGATION.'):
        assert rule in prompt, rule


def test_backtrace_prompt_superseded_revision_off_the_line():
    prompt = backtrace.compose(BT_CONTEXT, ['GAS-12'])
    assert "    Cites GAS-3 r1, no longer in force - its text is not on the project's line" in prompt


def test_backtrace_verdict_naming_the_live_row_of_its_subject():
    # plan 047 Phase 28 (A run 3, #54 BACKTRACE #358, #361, #363): after a REDEFINITION the prompt lists a CHANGED
    # requirement as "GAS-11 (now GAS-14)", and CC answered with the live reqId as the subject
    # plan 050 Phase 9 (fixture change): an OVER_REACH names its counterexample, or it is dropped
    answer = bt_answer(bt_verdict('GAS-10', 'OVER_REACH', counterexample='c'), bt_verdict('GAS-14', 'OVER_REACH', counterexample='c'),
                       bt_verdict('GAS-20', 'UNNEEDED'))
    assert [v['subject'] for v in backtrace.verdicts_of(answer, BT_CONTEXT, BT_CHUNK)['verdicts']] == \
        ['GAS-10', 'GAS-11', 'GAS-20'], 'the live row names its subject'
    with pytest.raises(ValueError) as e:
        backtrace.verdicts_of(bt_answer(bt_verdict('GAS-11', 'OVER_REACH'), bt_verdict('GAS-14', 'OVER_REACH'),
                                        bt_verdict('GAS-10', 'OVER_REACH'), bt_verdict('GAS-20', 'UNNEEDED')),
                              BT_CONTEXT, BT_CHUNK)
    assert 'names GAS-11 a second time' in str(e.value), 'the subject and its live row are one subject'


def test_backtrace_verdicts_canonical_in_chunk_order():
    raw = '```json\n' + bt_answer(
        bt_verdict('GAS-20', 'UNNEEDED', 'no NEED asks for periodic resends', needReqIds=[], needReqId=None),
        bt_verdict(' GAS-10 ', 'RESTS_ON_SUPERSEDED', ' rests on "settle" ', needReqId='GAS-2'),
        bt_verdict('GAS-11', 'JUSTIFIED', 'GAS-7 weighs sends', needReqIds=['GAS-7', 'GAS-2'])) + '\n```'
    assert backtrace.verdicts_of(raw, BT_CONTEXT, BT_CHUNK) == {'verdicts': [
        {'subject': 'GAS-10', 'verdict': 'RESTS_ON_SUPERSEDED', 'text': 'rests on "settle"', 'needReqId': 'GAS-2'},
        {'subject': 'GAS-11', 'verdict': 'JUSTIFIED', 'text': 'GAS-7 weighs sends', 'needReqIds': ['GAS-7', 'GAS-2']},
        {'subject': 'GAS-20', 'verdict': 'UNNEEDED', 'text': 'no NEED asks for periodic resends'},
    ]}
    other = backtrace.verdicts_of(bt_answer(
        bt_verdict('GAS-10', 'CONTRADICTS_NEED', 'a stale price', needReqId='GAS-2'),
        bt_verdict('GAS-11', 'OVER_REACH', '"at most once every 60 seconds"', counterexample='two prices 10 s apart'),
        bt_verdict('GAS-20', 'CONTRADICTS_NEED', 'resends cost', needReqId='GAS-7')), BT_CONTEXT, BT_CHUNK)
    assert [v['verdict'] for v in other['verdicts']] == ['CONTRADICTS_NEED', 'OVER_REACH', 'CONTRADICTS_NEED']
    assert 'needReqId' not in other['verdicts'][1]


@pytest.mark.parametrize('verdicts, message', [
    ([bt_verdict('GAS-10', 'OVER_REACH'), bt_verdict('GAS-11', 'OVER_REACH')], 'no verdict on GAS-20'),
    ([bt_verdict('GAS-12', 'OVER_REACH')], 'not a requirement of this chunk'),
    ([bt_verdict('GAS-10', 'OVER_REACH'), bt_verdict('GAS-10', 'OVER_REACH')], 'a second time'),
    ([bt_verdict('GAS-10', 'MAYBE')], 'unknown verdict'),
    ([bt_verdict('GAS-10', 'OVER_REACH', text=' ')], 'no text'),
    ([bt_verdict('GAS-10', 'OVER_REACH', kind='x')], 'unknown field'),
    ([bt_verdict('GAS-10', 'JUSTIFIED')], 'names no NEED'),
    ([bt_verdict('GAS-10', 'JUSTIFIED', needReqIds=['GAS-9'])], 'not one of the agreed NEEDs'),
    ([bt_verdict('GAS-10', 'JUSTIFIED', needReqIds=['GAS-2', 'GAS-2'])], 'twice'),
    ([bt_verdict('GAS-10', 'JUSTIFIED', needReqIds='GAS-2')], 'not a list'),
    ([bt_verdict('GAS-10', 'OVER_REACH', needReqId='GAS-2')], 'only CONTRADICTS_NEED and RESTS_ON_SUPERSEDED do'),
    ([bt_verdict('GAS-10', 'CONTRADICTS_NEED')], 'names no agreed NEED'),
    ([bt_verdict('GAS-10', 'CONTRADICTS_NEED', needReqId='GAS-3')], 'names no agreed NEED'),
    ([bt_verdict('GAS-10', 'CONTRADICTS_NEED', needReqId=7)], 'not a reqId'),
    ([bt_verdict('GAS-11', 'RESTS_ON_SUPERSEDED', needReqId='GAS-2')], 'no NEED it cites at a revision no longer in force'),
    ([bt_verdict('GAS-10', 'RESTS_ON_SUPERSEDED', needReqId='GAS-7')], 'no NEED it cites at a revision no longer in force'),
    ([bt_verdict('GAS-10', 'UNNEEDED')], "a held requirement's verdict only"),
    ([bt_verdict('GAS-20', 'OVER_REACH')], "an owned requirement's verdict only"),
])
def test_backtrace_check_refuses(verdicts, message):
    with pytest.raises(ValueError) as e:
        backtrace.verdicts_of(bt_answer(*verdicts), BT_CONTEXT, BT_CHUNK)
    assert message in str(e.value)


def test_backtrace_an_over_reach_and_its_counterexample():
    # plan 050 Phase 9 (decision 11) - characterization test: Green-1 pinned v7 (an OVER_REACH with no counterexample was in
    # the canonical answer); an OVER_REACH ("not necessary") needs a NEED-compliant situation the requirement forbids - the
    # check drops one without it; the subject still counts as answered
    out = backtrace.verdicts_of(bt_answer(bt_verdict('GAS-10', 'OVER_REACH', '"every station"'), bt_verdict('GAS-11', 'JUSTIFIED',
                                                    needReqIds=['GAS-2']), bt_verdict('GAS-20', 'UNNEEDED')), BT_CONTEXT, BT_CHUNK)
    assert [v['subject'] for v in out['verdicts']] == ['GAS-11', 'GAS-20'], 'the OVER_REACH without a counterexample is dropped'
    kept = backtrace.verdicts_of(bt_answer(
        bt_verdict('GAS-10', 'OVER_REACH', '"every station"', direction=' each station that is sent a price ',
                   counterexample=' a station that is never sent a price '),
        bt_verdict('GAS-11', 'JUSTIFIED', needReqIds=['GAS-2']),
        bt_verdict('GAS-20', 'CONTRADICTS_NEED', 'resends cost', needReqId='GAS-7', direction='resend on change only')),
        BT_CONTEXT, BT_CHUNK)['verdicts']
    assert kept[0] == {'subject': 'GAS-10', 'verdict': 'OVER_REACH', 'text': '"every station"',
                       'direction': 'each station that is sent a price', 'counterexample': 'a station that is never sent a price'}
    assert kept[2]['direction'] == 'resend on change only' and 'counterexample' not in kept[2]


def test_backtrace_check_refuses_a_non_object():
    with pytest.raises(ValueError) as e:
        backtrace.verdicts_of(json.dumps({'findings': []}), BT_CONTEXT, BT_CHUNK)
    assert 'no {"verdicts"' in str(e.value)


def test_backtrace_justified_without_text():
    # development run 244 (project #48): CC answered every JUSTIFIED with needReqIds only - the prompt asks for "only the
    # fields its verdict uses", and a JUSTIFIED verdict stores nothing
    raw = bt_answer({'subject': 'GAS-10', 'verdict': 'JUSTIFIED', 'needReqIds': ['GAS-2']},
                    bt_verdict('GAS-11', 'OVER_REACH', '"at most once every 60 seconds"', counterexample='two prices 10 s apart'),
                    {'subject': 'GAS-20', 'verdict': 'JUSTIFIED', 'needReqIds': ['GAS-7'], 'text': None})
    assert backtrace.verdicts_of(raw, BT_CONTEXT, BT_CHUNK) == {'verdicts': [
        {'subject': 'GAS-10', 'verdict': 'JUSTIFIED', 'needReqIds': ['GAS-2']},
        {'subject': 'GAS-11', 'verdict': 'OVER_REACH', 'text': '"at most once every 60 seconds"', 'counterexample': 'two prices 10 s apart'},
        {'subject': 'GAS-20', 'verdict': 'JUSTIFIED', 'needReqIds': ['GAS-7']},
    ]}, 'a JUSTIFIED verdict needs no text; every other verdict still does'


def test_backtrace_needs_named_by_a_verdict_other_than_justified():
    # plan 050 Phase 17 (#110 GASV8A9, AFTER_DEFINITION BACKTRACE: 8 of 9 attempts on GASV8A9-41; #108 GASV8A7 once): a
    # reasoning model names in needReqIds the NEEDs an OVER_REACH was measured against - the answer shape lists the field
    # for every verdict - and the check refused the whole chunk; every replacement was refused the same way, the group
    # stayed incomplete and the chain ended with no pass and no decline.
    # Characterization test: Green-1 pinned the refusal; the NEEDs of a verdict other than JUSTIFIED are no part of its
    # finding (only JUSTIFIED stores needReqIds), so the check drops them instead of refusing the chunk.
    raw = bt_answer(bt_verdict('GAS-10', 'OVER_REACH', '"every station"', needReqIds=['GAS-2'],
                               counterexample='a station that is never sent a price'),
                    bt_verdict('GAS-11', 'JUSTIFIED', needReqIds=['GAS-2']),
                    bt_verdict('GAS-20', 'UNNEEDED', needReqIds=['GAS-7']))
    assert backtrace.verdicts_of(raw, BT_CONTEXT, BT_CHUNK) == {'verdicts': [
        {'subject': 'GAS-10', 'verdict': 'OVER_REACH', 'text': '"every station"',
         'counterexample': 'a station that is never sent a price'},
        {'subject': 'GAS-11', 'verdict': 'JUSTIFIED', 'text': 'why', 'needReqIds': ['GAS-2']},
        {'subject': 'GAS-20', 'verdict': 'UNNEEDED', 'text': 'why'},
    ]}, 'needReqIds of a verdict other than JUSTIFIED are dropped, not refused'


@pytest.mark.parametrize('raw, message', [
    ('', 'the chunk names no subject'),
    ('GAS-10\nGAS-99', "'GAS-99', which is not a subject"),
    ('GAS-10\n\nGAS-10', 'twice'),
])
def test_backtrace_chunk_of_refuses(raw, message):
    with pytest.raises(ValueError) as e:
        backtrace.chunk_of(raw, BT_CONTEXT)
    assert message in str(e.value)


def test_backtrace_context_of():
    assert backtrace.chunk_of(' GAS-10 \n\nGAS-20\n', BT_CONTEXT) == ['GAS-10', 'GAS-20'], 'blank lines are skipped'
    assert backtrace.context_of(json.dumps(BT_CONTEXT))['snapshotId'] == 249
    for raw, message in (('not json', 'not JSON'), ('{"needs": []}', 'no needs and subjects'),
                         ('{"needs": [], "subjects": [{"held": true}]}', 'with no reqId')):
        with pytest.raises(ValueError) as e:
            backtrace.context_of(raw)
        assert message in str(e.value)
    assert backtrace.CHUNK_SIZE == 40
