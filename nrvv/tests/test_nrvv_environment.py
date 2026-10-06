# The simulated environment nrvv_env (plan 043, Phase 9): nrvv_environment and the Functions nrvv_env_prompt /
# nrvv_env_write - the prompt, every check of the writer, the write, and the placement under both pytest runs.

import json
import os
import subprocess
import sys

import pytest

import nrvv_env_prompt as ep
import nrvv_env_write as ew
import nrvv_environment as ne
import nrvv_suite_run as sr

INTERFACE = '{{METADATA}}x{{/METADATA}}{{M=1}}X-3 Set price\n{{M=2}}1.1) The service offers set_price(station, price).'
ENVIRONMENT = '{{M=1}}X-4 Out of order\n{{M=2}}1.1) The transport may deliver updates to one station out of order.'
DESIGN = {'interface': [{'reqId': 'X-3', 'content': INTERFACE}], 'environment': [{'reqId': 'X-4', 'content': ENVIRONMENT}]}

WORLD = '''import random


class World:
    """The simulated stations and transport around the server side."""

    def __init__(self, server, seed):
        self.rng = random.Random(seed)
        self.server = server
        self.displayed = {}

    def run(self):
        for station, price in self.server.updates():
            self.displayed[station] = price
'''

ANSWER = {'files': {'__init__.py': 'from .world import World\n', 'world.py': WORLD}}


# ---------------------------------------------------------------------------------------------------------- prompt

def test_env_prompt_carries_the_interface_the_environment_and_the_rules():
    prompt = ne.compose_env_prompt(ne.parse_design(json.dumps(DESIGN)))
    assert 'X-3:\nX-3 Set price\n1.1) The service offers set_price(station, price).' in prompt, 'plain text, markup gone'
    assert 'X-4:\nX-4 Out of order' in prompt
    assert prompt.index('The Interface') < prompt.index('X-3:') < prompt.index('The Environment') < prompt.index('X-4:')
    assert '`nrvv_env` never imports `app`' in prompt
    assert 'random.Random(seed)' in prompt
    assert 'never threading, _thread, multiprocessing, asyncio,' in prompt
    assert '{"files": {"__init__.py": "<content>", "<module>.py": "<content>"}}' in prompt


@pytest.mark.parametrize('bad', [
    'not json',
    '[]',
    json.dumps({'interface': [], 'environment': DESIGN['environment']}),
    json.dumps({'interface': DESIGN['interface']}),
    json.dumps({'interface': DESIGN['interface'], 'environment': [{'reqId': 'X-4', 'content': '  '}]}),
])
def test_parse_design_refuses_a_design_without_both_parts(bad):
    with pytest.raises(ValueError):
        ne.parse_design(bad)


# ---------------------------------------------------------------------------------------------------------- checks

def test_parse_env_answer_accepts_the_stdlib_the_package_and_relative_imports():
    files = dict(ANSWER['files'])
    files['clock.py'] = 'import nrvv_env.world\nfrom nrvv_env import world\nfrom collections import deque\nimport random as r\n'
    assert list(ne.parse_env_answer('```json\n' + json.dumps({'files': files}) + '\n```')) == ['__init__.py', 'clock.py', 'world.py']


@pytest.mark.parametrize('files, rule', [
    ({}, 'no JSON object'),
    ({'World.py': 'X = 1\n'}, 'is not a lowercase module name'),
    ({'world.txt': 'X = 1\n'}, 'is not a lowercase module name'),
    ({'../escape.py': 'X = 1\n'}, 'is not a lowercase module name'),
    ({'test_world.py': 'X = 1\n'}, 'would be collected by pytest'),
    ({'world_test.py': 'X = 1\n'}, 'would be collected by pytest'),
    ({'world.py': 'def broken(:\n'}, 'is not valid Python'),
    ({'world.py': 'import app\n'}, 'neither the standard library nor nrvv_env'),
    ({'world.py': 'import requests\n'}, 'neither the standard library nor nrvv_env'),
    ({'world.py': 'import threading\n'}, 'are forbidden'),
    ({'world.py': 'import _thread\n'}, 'are forbidden'),
    ({'world.py': 'from multiprocessing import Pool\n'}, 'are forbidden'),
    ({'world.py': 'import asyncio\n'}, 'are forbidden'),
    ({'world.py': 'from concurrent.futures import ThreadPoolExecutor\n'}, 'are forbidden'),
    ({'world.py': 'import time\n'}, 'are forbidden'),
    ({'world.py': 'def f():\n    import socket\n'}, 'are forbidden'),
    ({'world.py': 'import os, subprocess\n'}, 'are forbidden'),
])
def test_parse_env_answer_refuses_every_broken_rule(files, rule):
    with pytest.raises(ValueError) as e:
        ne.parse_env_answer(json.dumps({'files': files}))
    assert rule in str(e.value), str(e.value)


def test_parse_env_answer_refuses_what_is_not_a_files_map():
    for bad in ('not json', '[]', '{"files": []}', '{"files": {"world.py": 7}}'):
        with pytest.raises(ValueError):
            ne.parse_env_answer(bad)


# ---------------------------------------------------------------------------------------------------------- write

def test_write_env_replaces_the_package_and_adds_init(tmp_path):
    base = str(tmp_path / 'ts')
    old = os.path.join(base, 'tests', 'nrvv_env')
    os.makedirs(old)
    with open(os.path.join(old, 'stale.py'), 'w', encoding='utf-8') as f:
        f.write('STALE = 1\n')

    written = ne.write_env(base, 'nrvv/synthetic/gas-price/test-suite', {'world.py': WORLD})

    assert written == ['nrvv/synthetic/gas-price/test-suite/tests/nrvv_env/__init__.py',
                       'nrvv/synthetic/gas-price/test-suite/tests/nrvv_env/world.py']
    assert sorted(os.listdir(old)) == ['__init__.py', 'world.py'], 'the earlier package is gone'
    with open(os.path.join(old, 'world.py'), 'rb') as f:
        assert b'\r\n' not in f.read(), 'LF'


# ---------------------------------------------------------------------------------------------------------- placement

def sample_test_suite(tmp_path):
    """A test-suite dir holding nrvv_env (written by write_env), one test importing app and nrvv_env, and its suite;
    a target dir holding app."""
    ts = str(tmp_path / 'test-suite')
    target = str(tmp_path / 'target')
    os.makedirs(os.path.join(ts, 'suites'))
    os.makedirs(target)
    files = {
        os.path.join(ts, 'pytest.ini'): '[pytest]\naddopts = -p no:cacheprovider\n',
        os.path.join(ts, 'tests', 'test_sample.py'):
            'import app\nimport nrvv_env\n\n\ndef test_sample():\n    world = nrvv_env.World(app, seed=7)\n'
            '    world.run()\n    assert world.displayed == {"s1": 3}\n',
        os.path.join(ts, 'suites', 'sample.suite'): '# sample\ntests/test_sample.py::test_sample\n',
        os.path.join(target, 'app.py'): 'def updates():\n    return [("s1", 3)]\n',
    }
    for path, content in files.items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
    ne.write_env(ts, '', ne.parse_env_answer(json.dumps(ANSWER)))
    return ts, target


def test_nrvv_env_is_importable_under_the_launcher(tmp_path):
    ts, target = sample_test_suite(tmp_path)

    entry = sr.run_suite(ts, 'sample', target, str(tmp_path / 'verification'))

    assert entry['verdict'] == 'PASS', entry


def test_nrvv_env_is_importable_under_the_implementers_command(tmp_path):
    ts, target = sample_test_suite(tmp_path)

    # the implementer's session: cwd = the target dir, the target dir on PYTHONPATH, `python -m pytest <test-suite dir>`
    r = subprocess.run([sys.executable, '-m', 'pytest', ts, '-q'], cwd=target, capture_output=True, text=True,
                       env=dict(os.environ, PYTHONPATH=target, PYTHONDONTWRITEBYTECODE='1'))

    assert r.returncode == 0, r.stdout + r.stderr
    assert '1 passed' in r.stdout


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


def test_the_two_functions_through_their_roles(tmp_path):
    w1 = str(tmp_path / 'eprompt')
    ep.run(task_with_inputs(w1, [{'variable-for-design': 'design'}, {'variable-for-prompt': 'envPrompt'}],
                            {'design': json.dumps(DESIGN)}, ['envPrompt']))
    assert 'X-4 Out of order' in artifact(w1, 101)

    workspace = str(tmp_path / 'ws')
    os.makedirs(os.path.join(workspace, 'test-suite', 'nrvv', 'synthetic', 'gas-price', 'test-suite'))
    location = json.dumps({'url': 'https://example.com/a.git', 'branchOrRef': 'master',
                           'dir': 'nrvv/synthetic/gas-price/test-suite'})
    w2 = str(tmp_path / 'ewrite')
    ew.run(task_with_inputs(w2, [{'variable-for-workspace': 'workspace'}, {'variable-for-location': 'testSuite'},
                                 {'variable-for-cc-result': 'envResult'}, {'variable-for-files': 'envFiles'}],
                            {'workspace': workspace, 'testSuite': location, 'envResult': json.dumps(ANSWER)}, ['envFiles']))
    assert json.loads(artifact(w2, 101)) == ['nrvv/synthetic/gas-price/test-suite/tests/nrvv_env/__init__.py',
                                             'nrvv/synthetic/gas-price/test-suite/tests/nrvv_env/world.py']
