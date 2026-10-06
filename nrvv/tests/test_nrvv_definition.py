# The DEFINITION stage's prompts and checks (plan 043, Phase 8): nrvv_definition and the four Function scripts.

import json
import os

import pytest

import nrvv_decompose_check as dc
import nrvv_decompose_prompt as dp
import nrvv_definition as nd
import nrvv_design_check as gc
import nrvv_design_prompt as gp

# the decision 10 NEED of plan 043 - the synthetic NEED of the gas-price run
N1 = ('A central service publishes gas price updates to gas stations. A new desired price for a station can arrive '
      'while earlier updates to that station are still in flight. Updates can reach a station out of order; '
      'acknowledgements come back to the service in order. A station displays the last price it received and cannot '
      'be changed in any way. Every station must end up displaying the latest desired price for it, and the service '
      'must avoid sending unnecessary updates.')

NEEDS = [{'code': 'N-1', 'revision': 2, 'title': 'Gas stations settle on the latest price', 'statement': N1},
         {'code': 'N-2', 'revision': 1, 'title': 'Audit', 'statement': 'Every price sent is recorded.'}]
NEEDS_JSON = json.dumps(NEEDS)


def r_item(key, needs, statement='The service shall do it.'):
    return {'key': key, 'needs': needs, 'title': 'T ' + key, 'statement': statement, 'rationale': 'why ' + key}


def child(key, parent):
    return {'key': key, 'parent': parent, 'title': 'T ' + key, 'statement': 'S ' + key, 'rationale': 'why ' + key}


DECOMPOSITION = {'requirements': [r_item('R1', ['N-1']), r_item('R2', ['N-1', 'N-2'])]}
DESIGN = {'design': [child('D1', 'R1')], 'interface': [child('I1', 'R1')], 'environment': [child('E1', 'R2')]}


def checked_decomposition():
    return nd.check_decomposition(json.dumps(DECOMPOSITION), NEEDS)


# ---------------------------------------------------------------------------------------------------------- needs

def test_parse_needs_and_their_text():
    needs = nd.parse_needs(NEEDS_JSON)
    assert [n['code'] for n in needs] == ['N-1', 'N-2']
    text = nd.needs_text(needs)
    assert text.startswith('N-1 (revision 2) - Gas stations settle on the latest price\n' + N1)
    assert 'N-2 (revision 1) - Audit\nEvery price sent is recorded.' in text


@pytest.mark.parametrize('bad', ['', 'not json', '[]', '{"code": "N-1"}', '[{"code": "N-1"}]', '[{"statement": "s"}]'])
def test_parse_needs_refuses(bad):
    with pytest.raises(ValueError):
        nd.parse_needs(bad)


# ---------------------------------------------------------------------------------------------------------- prompts

def test_decompose_prompt_carries_every_need_and_the_answer_shape():
    prompt = nd.compose_decompose_prompt(NEEDS)
    assert N1 in prompt and 'Every price sent is recorded.' in prompt
    assert '"requirements": [{"key": "R1", "needs": ["N-1"]' in prompt
    assert 'what the system shall do - never how' in prompt
    assert '"assumed: <what you decided and why>"' in prompt, 'CC decides, and says so (decision 2)'
    assert 'name no programming language' in prompt, 'language-neutral (decision 8)'


def test_design_prompt_carries_the_needs_the_obligations_and_the_three_lists():
    prompt = nd.compose_design_prompt(NEEDS, checked_decomposition())
    assert N1 in prompt
    assert 'R2 - T R2 (restates N-1, N-2)\nThe service shall do it.' in prompt
    for shape in ('"design": [{"key": "D1", "parent": "R1"', '"interface": [{"key": "I1"', '"environment": [{"key": "E1"'):
        assert shape in prompt
    assert 'SERVER SIDE' in prompt and 'SIMULATE' in prompt
    assert 'any randomness is seeded, there is no wall clock and no real network' in prompt
    assert 'exactly ONE obligation' in prompt, 'DERIVATION is a tree (decision 6)'


# ---------------------------------------------------------------------------------------------------------- checks

def test_check_decomposition_strips_and_keeps_the_shape():
    raw = {'requirements': [dict(r_item('R1', [' N-1 ', 'N-1']), title='  Latest  '), r_item('R2', ['N-2'])]}
    checked = nd.check_decomposition('```json\n' + json.dumps(raw) + '\n```', NEEDS)
    assert checked['requirements'][0] == {'key': 'R1', 'needs': ['N-1'], 'title': 'Latest',
                                          'statement': 'The service shall do it.', 'rationale': 'why R1'}
    assert nd.to_json(checked).count('\n') == 0


@pytest.mark.parametrize('answer, rule', [
    ('not json', 'not JSON'),
    ('[]', 'no JSON object'),
    ('{}', "'requirements' is missing"),
    ('{"requirements": []}', 'no obligation'),
    (json.dumps({'requirements': ['R1']}), 'is not an object'),
    (json.dumps({'requirements': [dict(r_item('R1', ['N-1', 'N-2']), key='D1')]}), 'does not start with R'),
    (json.dumps({'requirements': [dict(r_item('R1', ['N-1', 'N-2']), statement=' ')]}), 'has no statement'),
    (json.dumps({'requirements': [r_item('R1', ['N-1', 'N-2']), r_item('R1', ['N-1'])]}), 'used twice'),
    (json.dumps({'requirements': [r_item('R1', []), r_item('R2', ['N-1', 'N-2'])]}), 'names no NEED'),
    (json.dumps({'requirements': [r_item('R1', ['N-1', 'N-2', 'N-7'])]}), "names NEED 'N-7'"),
    (json.dumps({'requirements': [r_item('R1', ['N-1'])]}), "no obligation restates NEED(s) ['N-2']"),
    (json.dumps({'requirements': [r_item('R1', ['N-1', ' '])]}), 'blank NEED code'),
])
def test_check_decomposition_refuses_every_broken_rule(answer, rule):
    with pytest.raises(ValueError) as e:
        nd.check_decomposition(answer, NEEDS)
    assert rule in str(e.value), str(e.value)


def test_check_design_passes_and_allows_no_design_item():
    checked = nd.check_design(json.dumps(DESIGN), checked_decomposition())
    assert [i['key'] for i in checked['interface']] == ['I1']
    assert checked['environment'][0]['parent'] == 'R2'
    assert nd.check_design(json.dumps(dict(DESIGN, design=[])), checked_decomposition())['design'] == []


@pytest.mark.parametrize('design, rule', [
    (dict(DESIGN, environment=[child('X1', 'R1')]), 'does not start with E'),
    (dict(DESIGN, interface=[child('I1', 'D1')]), "names parent 'D1'"),
    (dict(DESIGN, interface=[{'key': 'I1', 'title': 't', 'statement': 's', 'rationale': 'r'}]), "names parent 'None'"),
    (dict(DESIGN, design=[child('D1', 'R1'), child('D1', 'R2')]), 'used twice'),
    (dict(DESIGN, environment=[]), 'at least one Interface and one Environment'),
    (dict(DESIGN, interface=[]), 'at least one Interface and one Environment'),
    ({'design': [], 'interface': [child('I1', 'R1')]}, "'environment' is missing"),
])
def test_check_design_refuses_every_broken_rule(design, rule):
    with pytest.raises(ValueError) as e:
        nd.check_design(json.dumps(design), checked_decomposition())
    assert rule in str(e.value), str(e.value)


# ---------------------------------------------------------------------------------------------------------- the Functions

def task_with_inputs(working, metas, values, outputs):
    inputs = []
    for number, (name, text) in enumerate(values.items(), 1):
        os.makedirs(os.path.join(working, 'variable'), exist_ok=True)
        with open(os.path.join(working, 'variable', str(number)), 'w', encoding='utf-8') as f:
            f.write(text)
        inputs.append({'name': name, 'id': number, 'dataType': 'variable'})
    return {'workingPath': working, 'metas': metas, 'inputs': inputs,
            'outputs': [{'name': n, 'id': 100 + i} for i, n in enumerate(outputs, 1)]}


def artifact(working, output_id):
    with open(os.path.join(working, 'artifacts', str(output_id)), encoding='utf-8') as f:
        return f.read()


def test_the_four_functions_through_their_roles(tmp_path):
    w1 = str(tmp_path / 'dprompt')
    dp.run(task_with_inputs(w1, [{'variable-for-needs': 'needs'}, {'variable-for-prompt': 'decomposePrompt'}],
                            {'needs': NEEDS_JSON}, ['decomposePrompt']))
    assert N1 in artifact(w1, 101)

    w2 = str(tmp_path / 'dcheck')
    dc.run(task_with_inputs(w2, [{'variable-for-cc-result': 'decomposeResult'}, {'variable-for-needs': 'needs'},
                                 {'variable-for-decomposition': 'decomposition'}],
                            {'decomposeResult': json.dumps(DECOMPOSITION), 'needs': NEEDS_JSON}, ['decomposition']))
    decomposition = artifact(w2, 101)
    assert json.loads(decomposition)['requirements'][1]['needs'] == ['N-1', 'N-2']

    w3 = str(tmp_path / 'gprompt')
    gp.run(task_with_inputs(w3, [{'variable-for-needs': 'needs'}, {'variable-for-decomposition': 'decomposition'},
                                 {'variable-for-prompt': 'designPrompt'}],
                            {'needs': NEEDS_JSON, 'decomposition': decomposition}, ['designPrompt']))
    assert 'R1 - T R1 (restates N-1)' in artifact(w3, 101)

    w4 = str(tmp_path / 'gcheck')
    gc.run(task_with_inputs(w4, [{'variable-for-cc-result': 'designResult'}, {'variable-for-decomposition': 'decomposition'},
                                 {'variable-for-design': 'design'}],
                            {'designResult': json.dumps(DESIGN), 'decomposition': decomposition}, ['design']))
    assert json.loads(artifact(w4, 101))['interface'][0]['key'] == 'I1'
