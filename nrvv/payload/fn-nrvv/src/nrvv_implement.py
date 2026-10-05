# mh.asset.nrvv-implement_1.0 / _1.1 - ONE Claude Code session that writes the target-language implementation making
# the NRVV project's test suites pass (plan 042, Phases 11 and 13; nrvv/DETAILS.md, Implementation). Both codes run
# this script; _1.1 also binds the optional input `suites`, which _1.0 never has.
#
# Inputs  (process metas variable-for-<role>):
#   workspace    absolute path of the run workspace
#   test-suite   the test-suite location, JSON {"url", "branchOrRef", "dir"} - checked out before, read only here
#   target       the target location, JSON {"url", "branchOrRef", "dir"} - checked out before; the session's cwd
#   model        optional: the CC model, as mh.asset.call-cc reads it (NULLIFIED / absent = the CLI default)
#   effort       optional: the CC effort, likewise; 'ultracode' is refused
#   suites       optional (_1.1): JSON array of the suite names to make pass - the suites verifying the run's scope
#                (mhdg-nrvv.list-scope's scopeSuites). Absent, NULLIFIED or [] = every suite of the checkout. Every
#                named suite must be in the checkout; the others are named in the prompt as suites that must keep
#                passing, without their test files
# Meta:
#   timeout-sec  seconds allowed to the session; absent = 1800
# Output:
#   summary      the session's final message (never empty)
#
# CONFINEMENT - what the session can reach, decided here and nowhere else:
#   cwd          the target dir, created when the branch does not have it yet; no --add-dir, so CC's file tools have
#                no other directory
#   tools        Read, Write, Edit, Glob, Grep and Bash(python -m pytest:*) - nothing else is allowed in --print mode
#   MCP          --strict-mcp-config with no --mcp-config: no MCP server at all, not even one the box has configured
#   settings     ultracode off (--settings), as mh.asset.call-cc
# That confinement is an ASSUMPTION about the CLI; mh.asset.nrvv-guard_1.0, after this Function, is the CHECK
# (decision 17: a path check, not trust).
#
# THE TESTS ARE THE SPECIFICATION: the prompt carries every suite aimed at - every suite of the test-suite checkout
# unless `suites` names some - and the full text of every test file those suites name; the session may run the
# whole checkout with `python -m pytest`. Its environment puts the target dir on
# PYTHONPATH (where the suites find the implementation, as nrvv-suite-run does), the interpreter running this Function
# first on PATH (so the session's `python` has pytest), and PYTHONDONTWRITEBYTECODE=1 (no __pycache__ left in either
# checkout).
#
# It verifies nothing: the guard checks where the session wrote, the verification run checks what it wrote. ONE system
# call (DAHF 0.8).

import json
import os
import subprocess
import sys

import mh_task_io as io
import nrvv_paths
from nrvv_checkout import parse_location

FUNCTION_CODE = 'mh.asset.nrvv-implement'

CLAUDE_CODE_ENV_CODE = 'claude-code'
MH_ENV_FILE = 'mh-env.yaml'
SETTINGS_FILE = 'cc-settings.json'
PROMPT_FILE = 'cc-prompt.txt'
CONSOLE_LOG_FILE = 'cc-console.log'
DEFAULT_TIMEOUT_SEC = 1800
ULTRACODE_EFFORT = 'ultracode'
ALLOWED_TOOLS = ('Read', 'Write', 'Edit', 'Glob', 'Grep', 'Bash(python -m pytest:*)')
MAX_OUTPUT_LINES = 400
NO_SUMMARY = '(the session printed no summary)'


def posix(path):
    return str(path).replace('\\', '/')


def read_suites(test_suite_dir):
    """[(suite name, [ids])] of <test_suite_dir>/suites/*.suite, by name; a ValueError when there is none to aim at."""
    suites_dir = os.path.join(test_suite_dir, 'suites')
    if not os.path.isdir(suites_dir):
        raise ValueError('no suites dir in the test-suite checkout: ' + suites_dir)
    names = sorted(f[:-len('.suite')] for f in os.listdir(suites_dir) if f.endswith('.suite'))
    if not names:
        raise ValueError('the test-suite checkout has no suite to implement against: ' + suites_dir)
    suites = []
    for name in names:
        with open(os.path.join(suites_dir, name + '.suite'), encoding='utf-8') as f:
            ids = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        if not ids:
            raise ValueError('suite ' + name + ' lists no test')
        suites.append((name, ids))
    return suites


def parse_suite_names(text):
    """The suite names the input `suites` holds; None when there is no input (every suite). [] is every suite too.
    A ValueError for anything but a JSON array of non-blank strings."""
    if text is None or not text.strip():
        return None
    try:
        names = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError('suites is not JSON: ' + str(e))
    if not isinstance(names, list):
        raise ValueError('suites must be a JSON array of suite names, got ' + type(names).__name__)
    for name in names:
        if not isinstance(name, str) or not name.strip():
            raise ValueError('suites holds a value that is no suite name: ' + repr(name))
    return [name.strip() for name in names]


def select_suites(suites, names):
    """(the suites aimed at, the names of the other suites of the checkout). names None or [] aims at every suite;
    otherwise every name must be a suite of the checkout - a ValueError names the missing ones."""
    if not names:
        return list(suites), []
    present = [name for name, _ in suites]
    missing = [name for name in names if name not in present]
    if missing:
        raise ValueError('the test-suite checkout has no suite ' + ', '.join(missing)
                         + ' - the suites to make pass and the test-suite commit disagree')
    wanted = set(names)
    return [s for s in suites if s[0] in wanted], [name for name in present if name not in wanted]


def test_files(suites):
    """The test files the suites name (the part of each id before '::'), in order of first appearance."""
    files = []
    for _, ids in suites:
        for node_id in ids:
            rel = node_id.split('::', 1)[0]
            if rel not in files:
                files.append(rel)
    return files


def read_test_files(test_suite_dir, files):
    """{rel path: content}; a ValueError naming a file a suite lists but the checkout does not have."""
    texts = {}
    for rel in files:
        parts = nrvv_paths.rel_parts(rel)
        path = os.path.join(test_suite_dir, *parts)
        if not os.path.isfile(path):
            raise ValueError('a suite names ' + rel + ', which the test-suite checkout does not have')
        with open(path, encoding='utf-8') as f:
            texts[rel] = f.read()
    return texts


def compose_prompt(target_dir, test_suite_dir, suites, texts, others=()):
    target = posix(target_dir)
    ts = posix(test_suite_dir)
    lines = [
        'You implement a program in Python so that the test suites below pass.',
        '',
        'The tests are the specification. They are fixed: do not change, move, copy or delete any of them, and do not',
        'write anywhere but the current directory, which is the target directory:',
        '    ' + target,
        '',
        'What to deliver: the Python module or modules the tests import, written in the current directory - it is on',
        'PYTHONPATH when the tests run. Nothing else: no tests, no copies of tests, no build or packaging files.',
        '',
        'Check your work with exactly this command, as often as you need (single files: append tests/<file>.py):',
        '    python -m pytest ' + ts + ' -q',
        '',
        'Finish when every test listed below passes. End with a short summary of the files you wrote.',
        '',
    ]
    if others:
        lines += [
            'The checkout holds other suites as well. They are not listed here, and they must keep passing - the',
            'command above runs them too: ' + ', '.join(others),
            '',
        ]
    lines += [
        'Suites - every line a pytest node id, relative to ' + ts + ':',
    ]
    for name, ids in suites:
        lines.append(name + ':')
        lines.extend('    ' + node_id for node_id in ids)
    lines.append('')
    lines.append('Test files:')
    for rel, content in texts.items():
        lines.append('=== ' + rel + ' ===')
        lines.append(content.rstrip('\n'))
        lines.append('=== end of ' + rel + ' ===')
    return '\n'.join(lines) + '\n'


def cc_command(claude, settings_path, model=None, effort=None):
    """The session's argv. claude is the command prefix: [<the claude executable>] on a Processor."""
    if effort is not None and effort.strip() == ULTRACODE_EFFORT:
        raise ValueError("effort 'ultracode' is refused: it would switch ultracode on for the session")
    command = list(claude) + [
        '--print',
        '--output-format', 'text',
        '--strict-mcp-config',
        '--settings', settings_path,
        '--allowedTools', *ALLOWED_TOOLS,
    ]
    if model is not None and model.strip():
        command += ['--model', model.strip()]
    if effort is not None and effort.strip():
        command += ['--effort', effort.strip()]
    return command


def session_env(base_env, target_dir, python_exec):
    """The session's environment: base_env, with the target dir as PYTHONPATH, python_exec's dir first on PATH and
    no bytecode written."""
    env = dict(base_env)
    env['PYTHONPATH'] = target_dir
    env['PATH'] = os.path.dirname(os.path.abspath(python_exec)) + os.pathsep + env.get('PATH', '')
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return env


def resolve_env(envs, code):
    """The executable an env code names, in either shape mh-env.yaml is written in (as mh.asset.call-cc reads it)."""
    if isinstance(envs, dict):
        found = envs.get(code)
        available = sorted(envs)
    elif isinstance(envs, list):
        found = next((e.get('exec') for e in envs if isinstance(e, dict) and e.get('code') == code), None)
        available = sorted(str(e.get('code')) for e in envs if isinstance(e, dict))
    else:
        raise ValueError('envs in ' + MH_ENV_FILE + ' is neither a mapping nor a list')
    if found is None or not str(found).strip():
        raise ValueError("env code '" + code + "' not found in " + MH_ENV_FILE + '. Available: ' + str(available))
    return str(found).strip()


def timeout_sec(metas):
    value = io.meta_value(metas, 'timeout-sec')
    if value is None or not str(value).strip():
        return DEFAULT_TIMEOUT_SEC
    seconds = int(str(value).strip())
    if seconds < 1:
        raise ValueError('timeout-sec must be greater than 0, got ' + str(seconds))
    return seconds


def optional_role(task, role):
    """The text of an optional input bound by meta variable-for-<role>; None when the meta is absent or the input is
    NULLIFIED."""
    if io.meta_value(task.get('metas') or [], 'variable-for-' + role) is None:
        return None
    text = io.read_role(task, role)
    return text.strip() if text is not None and text.strip() else None


def tail_lines(text, max_lines=MAX_OUTPUT_LINES):
    lines = (text or '').splitlines()
    return '\n'.join(lines[-max_lines:])


def claude_from_processor(task):
    import yaml
    env_params = yaml.load(io.read_text(os.path.join(task['workingPath'], io.ARTIFACTS_DIR, MH_ENV_FILE)),
                           Loader=yaml.FullLoader)
    return [resolve_env(env_params.get('envs'), CLAUDE_CODE_ENV_CODE)]


def run(task, claude=None):
    """0 when the session ended normally and the summary was written; 1 otherwise (the reason printed)."""
    workspace = nrvv_paths.require_workspace((io.read_role(task, 'workspace') or '').strip())
    test_suite = parse_location(io.read_role(task, 'test-suite'))
    target = parse_location(io.read_role(task, 'target'))
    model = optional_role(task, 'model')
    effort = optional_role(task, 'effort')
    names = parse_suite_names(optional_role(task, 'suites'))
    summary_path = io.output_role(task, 'summary')   # resolved before the paid session

    test_suite_dir = nrvv_paths.dir_path(workspace, 'test-suite', test_suite['dir'])
    target_root = nrvv_paths.checkout_root(workspace, 'target')
    if not os.path.isdir(target_root):
        raise ValueError('the target checkout does not exist - was it checked out? ' + target_root)
    target_dir = nrvv_paths.dir_path(workspace, 'target', target['dir'])
    os.makedirs(target_dir, exist_ok=True)

    suites, others = select_suites(read_suites(test_suite_dir), names)
    texts = read_test_files(test_suite_dir, test_files(suites))
    prompt = compose_prompt(target_dir, test_suite_dir, suites, texts, others)

    work_dir = task['workingPath']
    os.makedirs(work_dir, exist_ok=True)
    prompt_file = os.path.join(work_dir, PROMPT_FILE)
    io.write_text(prompt_file, prompt)
    settings_file = os.path.join(work_dir, SETTINGS_FILE)
    io.write_text(settings_file, '{\n  "ultracode": false\n}')

    command = cc_command(claude if claude is not None else claude_from_processor(task), settings_file, model, effort)
    seconds = timeout_sec(task.get('metas') or [])
    print(FUNCTION_CODE + ': ' + str(len(suites)) + ' suite(s) aimed at, ' + str(len(others)) + ' other(s), '
          + str(len(texts)) + ' test file(s), cwd ' + target_dir)
    print('command: ' + str(command))
    print('model: ' + (model or '(CLI default)') + ', effort: ' + (effort or '(CLI default)') + ', timeout ' + str(seconds) + 's')

    try:
        with open(prompt_file, 'r', encoding='utf-8') as stdin_file:
            completed = subprocess.run(command, cwd=target_dir, stdin=stdin_file, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, timeout=seconds,
                                       env=session_env(os.environ, target_dir, sys.executable))
    except subprocess.TimeoutExpired:
        print('FAILED: the session did not finish within ' + str(seconds) + 's')
        return 1
    console = completed.stdout.decode('utf-8', errors='replace') if completed.stdout else ''
    io.write_text(os.path.join(work_dir, CONSOLE_LOG_FILE), console)
    print('--- session console ---\n' + tail_lines(console))
    print('exit code: ' + str(completed.returncode))
    if completed.returncode != 0:
        print('FAILED: the session exited with code ' + str(completed.returncode))
        return 1
    io.write_text(summary_path, console.strip() or NO_SUMMARY)
    return 0


def main(argv):
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is not None:
            reconfigure(encoding='utf-8', errors='backslashreplace')
    return run(io.load_params(argv)['task'])


if __name__ == '__main__':
    sys.exit(main(sys.argv))
