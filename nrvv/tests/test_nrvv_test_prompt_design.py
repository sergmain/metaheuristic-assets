# The test prompt's design mode (plan 043, Phase 10): with a design that has Interface items, the tests are written for
# the module `app` driven through the simulated environment nrvv_env; without one, the prompt is byte-identical to v1's.

import hashlib
import json
import os

import pytest

import nrvv_test_prompt as tp

# a RECOVERED requirement, as mhdg-rg.read-req hands it over (RG document markup), with its source citation
RECOVERED = ('{{METADATA}}INFO_BANK_DOCUMENT_NUMBER=3{{/METADATA}}\n{{M=1}}TMPSN3F36BJ-3 Greeting printed once\n'
             '{{M=100}}1. Requirement content\n{{M=2}}1.1) The program shall print "Hello, NRVV" exactly once when main runs.\n'
             '{{M=101}}2. Rationale\n{{M=3}}2.1) source: https://example.com/src.git@0123456789abcdef0123456789abcdef01234567:src/NrvvSample.java\n')
CRITERION = 'Running main prints "Hello, NRVV" exactly once.'

# the v1 prompt for RECOVERED, pinned BEFORE Phase 10 changed nrvv_test_prompt (043 savepoint): sha256 and length
V1_SHA256 = 'd3d0ea2f8846d5b2f41a8c4c87f1a6c659f62b21c1650951efc8a26152e2d4c9'
V1_LENGTH = 1689


def v1_prompt():
    return tp.compose('TMPSN3F36BJ-3', RECOVERED, CRITERION, 'TMPSN3F36BJ_3', 'TMPSN3F36BJ-9')


def test_the_v1_prompt_is_byte_identical():
    prompt = v1_prompt()
    assert len(prompt) == V1_LENGTH
    assert hashlib.sha256(prompt.encode('utf-8')).hexdigest() == V1_SHA256
    assert 'is the Python module `nrvv_sample`' in prompt, 'the module named by the source citation'


# ---------------------------------------------------------------------------------------------------------- design mode

DEFINED = '{{M=1}}X-1 Latest price\n{{M=100}}1. Requirement content\n{{M=2}}1.1) The service shall make every station display the latest desired price.\n'
INTERFACE = [{'reqId': 'X-3', 'content': '{{M=1}}X-3 Set price\n{{M=2}}1.1) The service offers set_price(station, price).'}]
ENV_FILES = {'__init__.py': 'from .world import World\n', 'world.py': 'import random\n\n\nclass World:\n    pass\n'}


def design_prompt():
    return tp.compose('X-1', DEFINED, 'The station displays 7 after set_price(s1, 7).', 'X_1', 'X-9', INTERFACE, ENV_FILES)


def test_design_mode_names_app_the_interface_and_nrvv_env_in_full():
    prompt = design_prompt()
    assert 'is the Python module `app`, importable as `import app`' in prompt
    assert 'snake_case function or method of `app`' in prompt and 'CapWords class of `app`' in prompt
    assert 'The Interface of `app`:\n\nX-3:\nX-3 Set price\n1.1) The service offers set_price(station, price).' in prompt
    assert '--- tests/nrvv_env/__init__.py\nfrom .world import World' in prompt
    assert '--- tests/nrvv_env/world.py\nimport random\n\n\nclass World:\n    pass' in prompt
    assert 'drives `app` only through `nrvv_env` - no other fake' in prompt
    assert 'fixed seeds only (several seeds per property are allowed)' in prompt
    assert 'ported' not in prompt and 'nrvv_sample' not in prompt, 'a defined system is not a port'
    assert '{"testFile": "<the whole content of tests/test_X_1.py>"}' in prompt


def test_a_design_without_env_files_is_refused():
    with pytest.raises(ValueError):
        tp.compose('X-1', DEFINED, 'c', 'X_1', 'X-9', INTERFACE, {})


def test_interface_items():
    assert tp.interface_items(None) == []
    assert tp.interface_items('  ') == []
    assert tp.interface_items(json.dumps({'interface': [], 'environment': []})) == []
    assert tp.interface_items(json.dumps({'interface': INTERFACE, 'environment': []})) == INTERFACE
    for bad in ('not json', '[]', '{"environment": []}'):
        with pytest.raises(ValueError):
            tp.interface_items(bad)


def test_read_env_files(tmp_path):
    with pytest.raises(ValueError):
        tp.read_env_files(str(tmp_path))
    env = tmp_path / 'tests' / 'nrvv_env'
    env.mkdir(parents=True)
    (env / 'world.py').write_text('W = 1\n', encoding='utf-8')
    (env / '__init__.py').write_text('', encoding='utf-8')
    (env / 'notes.txt').write_text('not python', encoding='utf-8')
    assert tp.read_env_files(str(tmp_path)) == {'__init__.py': '', 'world.py': 'W = 1\n'}


# ---------------------------------------------------------------------------------------------------------- run()

V1_METAS = [{'variable-for-req-id': 'reqId'}, {'variable-for-requirement': 'requirementContent'},
            {'variable-for-criterion': 'testCaseCriterion'}, {'variable-for-suite-name': 'suiteName'},
            {'variable-for-test-case-req-id': 'testCaseReqId'}, {'variable-for-prompt': 'testPrompt'}]


def task_with_inputs(working, metas, values, outputs, nullified=()):
    inputs = []
    for number, (name, text) in enumerate(values.items(), 1):
        os.makedirs(os.path.join(working, 'variable'), exist_ok=True)
        if name in nullified:
            inputs.append({'name': name, 'id': number, 'dataType': 'variable', 'empty': True})
            continue
        with open(os.path.join(working, 'variable', str(number)), 'w', encoding='utf-8') as f:
            f.write(text)
        inputs.append({'name': name, 'id': number, 'dataType': 'variable'})
    return {'workingPath': working, 'metas': metas, 'inputs': inputs,
            'outputs': [{'name': n, 'id': 100 + i} for i, n in enumerate(outputs, 1)]}


def prompt_of(working):
    with open(os.path.join(working, 'artifacts', '101'), encoding='utf-8') as f:
        return f.read()


V1_VALUES = {'reqId': 'TMPSN3F36BJ-3', 'requirementContent': RECOVERED, 'testCaseCriterion': CRITERION,
             'suiteName': 'TMPSN3F36BJ_3', 'testCaseReqId': 'TMPSN3F36BJ-9'}


def test_run_without_the_design_roles_is_v1(tmp_path):
    w = str(tmp_path / 'v1')
    tp.run(task_with_inputs(w, V1_METAS, V1_VALUES, ['testPrompt']))
    assert hashlib.sha256(prompt_of(w).encode('utf-8')).hexdigest() == V1_SHA256


def test_run_with_a_design_without_interface_or_nullified_is_v1(tmp_path):
    metas = V1_METAS + [{'variable-for-design': 'design'}, {'variable-for-env-dir': 'testSuiteDir'}]
    no_design = json.dumps({'interface': [], 'environment': []})
    for case, values, nullified in (('empty', dict(V1_VALUES, design=no_design, testSuiteDir='unused'), ()),
                                    ('nullified', dict(V1_VALUES, design='', testSuiteDir='unused'), ('design',))):
        w = str(tmp_path / case)
        tp.run(task_with_inputs(w, metas, values, ['testPrompt'], nullified))
        assert hashlib.sha256(prompt_of(w).encode('utf-8')).hexdigest() == V1_SHA256, case


def test_run_in_design_mode_reads_nrvv_env_from_the_checkout(tmp_path):
    ts = tmp_path / 'ws' / 'test-suite' / 'nrvv' / 'synthetic' / 'gas-price' / 'test-suite'
    (ts / 'tests' / 'nrvv_env').mkdir(parents=True)
    for name, source in ENV_FILES.items():
        (ts / 'tests' / 'nrvv_env' / name).write_text(source, encoding='utf-8')
    metas = V1_METAS + [{'variable-for-design': 'design'}, {'variable-for-env-dir': 'testSuiteDir'}]
    values = {'reqId': 'X-1', 'requirementContent': DEFINED, 'testCaseCriterion': 'The station displays 7.',
              'suiteName': 'X_1', 'testCaseReqId': 'X-9',
              'design': json.dumps({'interface': INTERFACE, 'environment': []}), 'testSuiteDir': str(ts) + '\n'}
    w = str(tmp_path / 'design')

    tp.run(task_with_inputs(w, metas, values, ['testPrompt']))

    assert prompt_of(w) == tp.compose('X-1', DEFINED, 'The station displays 7.', 'X_1', 'X-9', INTERFACE, ENV_FILES)
