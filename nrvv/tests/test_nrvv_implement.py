# mh.asset.nrvv-implement_1.0 (plan 042, Phase 11): which suites and test files the session is given, its prompt, its
# command line (the confinement), its environment - and run() end to end with a stand-in for the `claude` executable,
# which no test can run for real (a process exec, the one place a stand-in has no real counterpart). The stand-in
# records how it was started and writes a module where it was started; the real launcher then runs the suite against
# what it wrote. Every path is built under the test's own tmp_path.

import json
import os
import sys

import pytest

import nrvv_implement as im
import nrvv_suite_run as launcher
from conftest import write

URL = 'https://github.com/sergmain/metaheuristic-assets.git'
SUITE = 'TMPSN3F36BJ_12_suite'
TEST_FILE = 'tests/test_' + SUITE + '.py'
TESTS = ("import nrvv_sample\n\n\ndef test_main_prints_hello(capsys):\n    nrvv_sample.NrvvSample().main()\n"
         "    assert capsys.readouterr().out == 'Hello, NRVV\\n'\n")


def suite_dir_with(root, suites=None, files=None):
    write(root, files if files is not None else {TEST_FILE: TESTS, 'pytest.ini': '[pytest]\naddopts = -p no:cacheprovider\n'})
    write(root, suites if suites is not None else
          {'suites/' + SUITE + '.suite': '# ' + SUITE + '\n' + TEST_FILE + '::test_main_prints_hello\n'})
    return root


# ---------------------------------------------------------------------------------------------------
# what the session is given

def test_read_suites_lists_every_suite_by_name_and_skips_comments(tmp_path):
    ts = suite_dir_with(str(tmp_path / 'ts'), suites={
        'suites/B_2_suite.suite': '# b\ntests/test_B_2_suite.py::test_b\n\n',
        'suites/A_1_suite.suite': 'tests/test_A_1_suite.py::test_a\ntests/test_A_1_suite.py::test_c\n',
        'suites/notes.txt': 'not a suite\n'})

    assert im.read_suites(ts) == [('A_1_suite', ['tests/test_A_1_suite.py::test_a', 'tests/test_A_1_suite.py::test_c']),
                                  ('B_2_suite', ['tests/test_B_2_suite.py::test_b'])]


def test_read_suites_refuses_a_checkout_without_suites(tmp_path):
    os.makedirs(tmp_path / 'ts' / 'suites')
    with pytest.raises(ValueError, match='no suite'):
        im.read_suites(str(tmp_path / 'ts'))
    with pytest.raises(ValueError, match='no suites dir'):
        im.read_suites(str(tmp_path / 'none'))


def test_read_suites_refuses_a_suite_that_lists_nothing(tmp_path):
    ts = suite_dir_with(str(tmp_path / 'ts'), suites={'suites/A_1_suite.suite': '# only a comment\n'})
    with pytest.raises(ValueError, match='lists no test'):
        im.read_suites(ts)


def test_test_files_are_the_files_the_ids_name_once_each_in_order():
    suites = [('A', ['tests/a.py::t1', 'tests/a.py::t2']), ('B', ['tests/b.py::t3', 'tests/a.py::t4'])]

    assert im.test_files(suites) == ['tests/a.py', 'tests/b.py']


def test_read_test_files_refuses_a_file_a_suite_names_but_the_checkout_lacks(tmp_path):
    ts = suite_dir_with(str(tmp_path / 'ts'))
    assert im.read_test_files(ts, [TEST_FILE]) == {TEST_FILE: TESTS}
    with pytest.raises(ValueError, match='does not have'):
        im.read_test_files(ts, ['tests/test_missing.py'])


def test_the_prompt_carries_the_target_dir_the_command_every_suite_and_every_test_file():
    prompt = im.compose_prompt('C:\\ws\\target\\nrvv\\synthetic\\target', 'C:\\ws\\test-suite\\ts',
                               [(SUITE, [TEST_FILE + '::test_main_prints_hello'])], {TEST_FILE: TESTS})

    assert '    C:/ws/target/nrvv/synthetic/target\n' in prompt
    assert '    python -m pytest C:/ws/test-suite/ts -q\n' in prompt
    assert SUITE + ':\n    ' + TEST_FILE + '::test_main_prints_hello\n' in prompt
    assert '=== ' + TEST_FILE + ' ===\n' + TESTS.rstrip('\n') + '\n=== end of ' + TEST_FILE + ' ===' in prompt
    assert 'do not change, move, copy or delete' in prompt


# ---------------------------------------------------------------------------------------------------
# the confinement

def test_the_command_confines_the_session():
    command = im.cc_command(['claude'], 'C:/task/cc-settings.json', ' claude-opus-4-8 ', 'medium')

    assert command[0] == 'claude'
    assert '--print' in command and '--strict-mcp-config' in command
    assert command[command.index('--settings') + 1] == 'C:/task/cc-settings.json'
    allowed = command[command.index('--allowedTools') + 1:command.index('--allowedTools') + 1 + len(im.ALLOWED_TOOLS)]
    assert allowed == ['Read', 'Write', 'Edit', 'Glob', 'Grep', 'Bash(python -m pytest:*)']
    assert '--add-dir' not in command and '--mcp-config' not in command
    assert '--dangerously-skip-permissions' not in command
    assert command[command.index('--model') + 1] == 'claude-opus-4-8'
    assert command[command.index('--effort') + 1] == 'medium'


def test_the_command_omits_an_absent_model_and_effort_and_refuses_ultracode():
    command = im.cc_command(['claude'], 's.json', None, '  ')
    assert '--model' not in command and '--effort' not in command
    with pytest.raises(ValueError, match='ultracode'):
        im.cc_command(['claude'], 's.json', 'm', 'ultracode')


def test_the_session_environment():
    env = im.session_env({'PATH': 'C:/bin', 'PYTHONPATH': 'C:/elsewhere', 'X': 'y'}, 'C:/ws/target/tg', 'C:/py/python.exe')

    assert env['PYTHONPATH'] == 'C:/ws/target/tg'
    assert env['PATH'].split(os.pathsep)[0] == os.path.dirname(os.path.abspath('C:/py/python.exe'))
    assert env['PATH'].endswith('C:/bin')
    assert env['PYTHONDONTWRITEBYTECODE'] == '1'
    assert env['X'] == 'y'


@pytest.mark.parametrize('envs', [{'claude-code': 'C:/cc/claude.exe', 'python-3': 'p'},
                                  [{'code': 'python-3', 'exec': 'p'}, {'code': 'claude-code', 'exec': 'C:/cc/claude.exe'}]])
def test_resolve_env_reads_both_shapes_of_mh_env(envs):
    assert im.resolve_env(envs, 'claude-code') == 'C:/cc/claude.exe'


def test_resolve_env_names_what_is_available_when_the_code_is_missing():
    with pytest.raises(ValueError, match="python-3"):
        im.resolve_env({'python-3': 'p'}, 'claude-code')


# ---------------------------------------------------------------------------------------------------
# run(), with a stand-in for the claude executable

FAKE_CLAUDE = '''import json, os, sys
prompt = sys.stdin.read()
with open(os.environ["NRVV_FAKE_RECORD"], "w", encoding="utf-8") as f:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "pythonpath": os.environ.get("PYTHONPATH"),
               "nobytecode": os.environ.get("PYTHONDONTWRITEBYTECODE"), "prompt": prompt}, f)
with open("nrvv_sample.py", "w", encoding="utf-8") as f:
    f.write(os.environ["NRVV_FAKE_MODULE"])
print("wrote nrvv_sample.py")
sys.exit(int(os.environ.get("NRVV_FAKE_EXIT", "0")))
'''

GOOD_MODULE = "class NrvvSample:\n    def main(self):\n        print('Hello, NRVV')\n"

METAS = [{'variable-for-workspace': 'workspace'}, {'variable-for-test-suite': 'testSuite'},
         {'variable-for-target': 'target'}, {'variable-for-model': 'model'}, {'variable-for-effort': 'effort'},
         {'variable-for-summary': 'implementSummary'}, {'timeout-sec': '120'}]


def task_with_inputs(working, values, empty=()):
    inputs = []
    for number, (name, text) in enumerate(values.items(), 1):
        os.makedirs(os.path.join(working, 'variable'), exist_ok=True)
        if name not in empty:
            with open(os.path.join(working, 'variable', str(number)), 'w', encoding='utf-8') as f:
                f.write(text)
        inputs.append({'name': name, 'id': number, 'dataType': 'variable', 'empty': name in empty})
    return {'workingPath': working, 'metas': METAS, 'inputs': inputs, 'outputs': [{'name': 'implementSummary', 'id': 101}]}


def implement(tmp_path, monkeypatch, module=GOOD_MODULE, exit_code=0):
    workspace = str(tmp_path / 'ws')
    suite_dir_with(os.path.join(workspace, 'test-suite', 'nrvv', 'synthetic', 'test-suite'))
    os.makedirs(os.path.join(workspace, 'target'))                       # the checkout exists, its dir does not
    fake = tmp_path / 'fake_claude.py'
    fake.write_text(FAKE_CLAUDE, encoding='utf-8')
    record = tmp_path / 'record.json'
    monkeypatch.setenv('NRVV_FAKE_RECORD', str(record))
    monkeypatch.setenv('NRVV_FAKE_MODULE', module)
    monkeypatch.setenv('NRVV_FAKE_EXIT', str(exit_code))
    working = str(tmp_path / 'task')
    task = task_with_inputs(working, {
        'workspace': workspace + '\n',
        'testSuite': json.dumps({'url': URL, 'branchOrRef': 'nrvv-synthetic-test-suite', 'dir': 'nrvv/synthetic/test-suite'}),
        'target': json.dumps({'url': URL, 'branchOrRef': 'nrvv-synthetic-target', 'dir': 'nrvv/synthetic/target'}),
        'model': 'claude-opus-4-8\n', 'effort': ''}, empty=('effort',))
    code = im.run(task, claude=[sys.executable, str(fake)])
    with open(record, encoding='utf-8') as f:
        recorded = json.load(f)
    return code, workspace, working, recorded


def test_run_starts_the_session_in_the_target_dir_and_stores_its_summary(tmp_path, monkeypatch):
    code, workspace, working, recorded = implement(tmp_path, monkeypatch)

    target_dir = os.path.join(workspace, 'target', 'nrvv', 'synthetic', 'target')
    assert code == 0
    assert os.path.normcase(recorded['cwd']) == os.path.normcase(target_dir)
    assert recorded['pythonpath'] == target_dir
    assert recorded['nobytecode'] == '1'
    assert '--strict-mcp-config' in recorded['argv'] and '--add-dir' not in recorded['argv']
    assert recorded['argv'][recorded['argv'].index('--model') + 1] == 'claude-opus-4-8'
    assert '--effort' not in recorded['argv'], 'a NULLIFIED effort omits the flag'
    assert SUITE in recorded['prompt'] and TESTS.rstrip('\n') in recorded['prompt']
    with open(os.path.join(working, 'artifacts', '101'), encoding='utf-8') as f:
        assert f.read() == 'wrote nrvv_sample.py'
    assert os.path.isfile(os.path.join(target_dir, 'nrvv_sample.py'))


def test_what_the_session_wrote_is_what_the_launcher_runs_the_suite_against(tmp_path, monkeypatch):
    _, workspace, _, _ = implement(tmp_path, monkeypatch)

    entry = launcher.run_suite(os.path.join(workspace, 'test-suite', 'nrvv', 'synthetic', 'test-suite'), SUITE,
                               os.path.join(workspace, 'target', 'nrvv', 'synthetic', 'target'), str(tmp_path / 'out'))

    assert entry['verdict'] == 'PASS', entry


def test_run_fails_when_the_session_fails_and_stores_no_summary(tmp_path, monkeypatch):
    code, _, working, _ = implement(tmp_path, monkeypatch, exit_code=3)

    assert code == 1
    assert not os.path.exists(os.path.join(working, 'artifacts', '101'))


def test_run_refuses_a_missing_target_checkout(tmp_path):
    working = str(tmp_path / 'task')
    task = task_with_inputs(working, {
        'workspace': str(tmp_path / 'ws'),
        'testSuite': json.dumps({'url': URL, 'branchOrRef': 'b', 'dir': ''}),
        'target': json.dumps({'url': URL, 'branchOrRef': 'b', 'dir': ''}),
        'model': 'm', 'effort': 'medium'})
    with pytest.raises(ValueError, match='target checkout does not exist'):
        im.run(task, claude=[sys.executable, '-c', 'pass'])
