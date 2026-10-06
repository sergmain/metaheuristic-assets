# The implementation prompt's design mode (plan 043, Phase 11): with a design that has Interface items, the prompt
# carries the Interface and the files of tests/nrvv_env/ as fixed parts of the tests and names `app` as the module to
# deliver; without one, the prompt is byte-identical to v1's.

import hashlib
import json
import os
import sys

import nrvv_implement as im

TARGET = 'C:/ws/target/nrvv/target'
TEST_SUITE = 'C:/ws/test-suite/nrvv/test-suite'
SUITES = [('X_1', ['tests/test_X_1.py::test_a', 'tests/test_X_1.py::test_b']), ('X_2', ['tests/test_X_2.py'])]
TEXTS = {'tests/test_X_1.py': 'import app\n\n\ndef test_a():\n    assert app.f() == 1\n', 'tests/test_X_2.py': 'def test_c():\n    pass\n'}

# the v1 prompt for these inputs, pinned BEFORE Phase 11 changed nrvv_implement (043 savepoint): sha256 and length
V1_SHA256 = 'e94c886603b8c07e47dbae6bb415fd76ae22cd99fbf7db19aec768881bddcb1b'
V1_LENGTH = 1267


def test_the_v1_prompt_is_byte_identical():
    prompt = im.compose_prompt(TARGET, TEST_SUITE, SUITES, TEXTS, ['X_3'])
    assert len(prompt) == V1_LENGTH
    assert hashlib.sha256(prompt.encode('utf-8')).hexdigest() == V1_SHA256


# ---------------------------------------------------------------------------------------------------------- design mode

INTERFACE = [{'reqId': 'X-3', 'content': '{{M=1}}X-3 Set price\n{{M=2}}1.1) The service offers set_price(station, price).'}]
ENV_FILES = {'__init__.py': 'from .world import World\n', 'world.py': 'class World:\n    pass\n'}


def test_design_mode_names_app_and_carries_the_interface_and_nrvv_env():
    prompt = im.compose_prompt(TARGET, TEST_SUITE, SUITES, TEXTS, ['X_3'], INTERFACE, ENV_FILES)
    assert 'What to deliver: the Python module `app`' in prompt
    assert 'snake_case function or method' in prompt and 'CapWords class of `app`' in prompt
    assert 'It is a fixed part of the tests: do not change, copy or imitate it.' in prompt
    assert '=== X-3 ===\nX-3 Set price\n1.1) The service offers set_price(station, price).\n=== end of X-3 ===' in prompt
    assert '=== tests/nrvv_env/world.py ===\nclass World:\n    pass\n=== end of tests/nrvv_env/world.py ===' in prompt
    assert '=== tests/test_X_1.py ===' in prompt, 'the test files stay'
    assert 'the Python module or modules the tests import' not in prompt


def test_no_interface_is_v1():
    assert im.compose_prompt(TARGET, TEST_SUITE, SUITES, TEXTS, ['X_3'], [], None) == \
        im.compose_prompt(TARGET, TEST_SUITE, SUITES, TEXTS, ['X_3'])


# ---------------------------------------------------------------------------------------------------------- run()

def checkouts(tmp_path, with_env):
    ws = tmp_path / 'ws'
    ts = ws / 'test-suite' / 'ts'
    (ts / 'suites').mkdir(parents=True)
    (ts / 'tests').mkdir()
    (ts / 'suites' / 'X_1.suite').write_text('tests/test_X_1.py::test_a\n', encoding='utf-8')
    (ts / 'tests' / 'test_X_1.py').write_text(TEXTS['tests/test_X_1.py'], encoding='utf-8')
    if with_env:
        (ts / 'tests' / 'nrvv_env').mkdir()
        for name, source in ENV_FILES.items():
            (ts / 'tests' / 'nrvv_env' / name).write_text(source, encoding='utf-8')
    (ws / 'target').mkdir(parents=True)
    return str(ws)


def task(working, workspace, design=None):
    values = {'workspace': workspace,
              'testSuite': json.dumps({'url': 'u', 'branchOrRef': 'master', 'dir': 'ts'}),
              'target': json.dumps({'url': 'u', 'branchOrRef': 'master', 'dir': 't'})}
    metas = [{'variable-for-workspace': 'workspace'}, {'variable-for-test-suite': 'testSuite'},
             {'variable-for-target': 'target'}, {'variable-for-summary': 'summary'}]
    if design is not None:
        values['design'] = design
        metas.append({'variable-for-design': 'design'})
    inputs = []
    for number, (name, text) in enumerate(values.items(), 1):
        os.makedirs(os.path.join(working, 'variable'), exist_ok=True)
        with open(os.path.join(working, 'variable', str(number)), 'w', encoding='utf-8') as f:
            f.write(text)
        inputs.append({'name': name, 'id': number, 'dataType': 'variable'})
    return {'workingPath': working, 'metas': metas, 'inputs': inputs, 'outputs': [{'name': 'summary', 'id': 101}]}


def session_prompt(working):
    with open(os.path.join(working, im.PROMPT_FILE), encoding='utf-8') as f:
        return f.read()


def test_run_with_a_design_gives_the_session_the_design_mode_prompt(tmp_path):
    workspace = checkouts(tmp_path, with_env=True)
    w = str(tmp_path / 'design')

    assert im.run(task(w, workspace, json.dumps({'interface': INTERFACE, 'environment': []})),
                  claude=[sys.executable, '-c', 'pass']) == 0

    prompt = session_prompt(w)
    assert 'What to deliver: the Python module `app`' in prompt
    assert '=== tests/nrvv_env/__init__.py ===\nfrom .world import World' in prompt


def test_run_without_a_design_or_with_an_empty_one_is_v1(tmp_path):
    workspace = checkouts(tmp_path, with_env=False)
    prompts = []
    for case, design in (('none', None), ('empty', json.dumps({'interface': [], 'environment': []}))):
        w = str(tmp_path / case)
        assert im.run(task(w, workspace, design), claude=[sys.executable, '-c', 'pass']) == 0
        prompts.append(session_prompt(w))
    assert prompts[0] == prompts[1]
    assert 'the Python module or modules the tests import' in prompts[0]
