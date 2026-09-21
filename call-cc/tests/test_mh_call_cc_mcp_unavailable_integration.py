# An integration test: run mh.asset.call-cc's REAL main() with the `claude` CLI replaced by a fake python script,
# and prove what the Function does around the CC call:
#
#   1. ultracode is off and the MCP-unavailable rule is on CC's system prompt - both handed over as files, by bare
#      name, and both files really written into the task dir;
#   2. a model that reports the MCP server unavailable ends the Function IMMEDIATELY with a NEGATIVE exit code -
#      while CC itself exits 0, exactly as it does when the model simply ends its turn;
#   3. a healthy run whose console ECHOES the whole rule, template line included, still succeeds.
#
# Same shape as test_mh_call_cc_console_log_integration.py: no doubles and no monkeypatching of production - a
# real fake `claude` executable, run the way a Processor runs `claude`.

import contextlib
import io
import json
import os
import stat
import sys

import mh_call_cc

# The head of every fake: record argv beside the script (the flags CC was given), drain the prompt on stdin.
# Bytes via stdout.buffer: the fake's own stdout is a pipe, and text mode would hit cp1252 - not this test's subject.
FAKE_HEAD = (
    "import json, os, sys\n"
    "here = os.path.dirname(os.path.abspath(__file__))\n"
    "with open(os.path.join(here, 'cc-argv.json'), 'w', encoding='utf-8') as f:\n"
    "    json.dump(sys.argv[1:], f)\n"
    "sys.stdin.buffer.read()\n"
    "def say(text):\n"
    "    sys.stdout.buffer.write((text + '\\n').encode('utf-8'))\n"
)

# The model found the MCP server gone: one line, end of turn. No result is stored, and CC itself exits 0.
UNAVAILABLE_FAKE = FAKE_HEAD + (
    "say('[DEBUG] MCP server \"mhcc\": Connection failed')\n"
    "say('MCP_UNAVAILABLE: CONNECTION_CLOSED')\n"
    "say('[DEBUG] Cleaning up MCP servers')\n"
    "sys.stdout.buffer.flush()\n"
    "sys.exit(0)\n"
)

# A healthy run: the console echoes the whole system prompt file it was handed, and the answer is stored where
# the MCP server stores it - cc-data/cc-result.out under the task dir, which is this process's cwd.
HEALTHY_FAKE = FAKE_HEAD + (
    "args = sys.argv[1:]\n"
    "with open(args[args.index('--append-system-prompt-file') + 1], encoding='utf-8') as f:\n"
    "    say(f.read())\n"
    "os.makedirs('cc-data', exist_ok=True)\n"
    "with open(os.path.join('cc-data', 'cc-result.out'), 'w', encoding='utf-8') as f:\n"
    "    f.write('the answer')\n"
    "sys.stdout.buffer.flush()\n"
    "sys.exit(0)\n"
)


def _write(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _fake_claude(scripts_dir, script):
    """A real executable that runs the fake under this interpreter, the way a Processor runs `claude`."""
    fake = scripts_dir / 'fake_cc.py'
    _write(fake, script)
    if os.name == 'nt':
        shim = scripts_dir / 'claude.cmd'
        _write(shim, '@"{}" "{}" %*\n'.format(sys.executable, fake))
    else:
        shim = scripts_dir / 'claude'
        _write(shim, '#!/bin/sh\nexec "{}" "{}" "$@"\n'.format(sys.executable, fake))
        os.chmod(shim, os.stat(shim).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return shim


def _task(tmp_path, script):
    """(work, scripts, params_path) - a minimal but real task tree whose mh-env.yaml names the fake claude.
    Single-quoted YAML scalars so a Windows path's backslashes stay literal."""
    work = tmp_path / 'task'
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (work / 'variable').mkdir(parents=True)
    _write(work / 'variable' / '1', 'derive requirements from this file')
    (work / 'artifacts').mkdir(parents=True)
    _write(work / 'artifacts' / 'mh-env.yaml', "envs:\n  claude-code: '{}'\n".format(_fake_claude(scripts, script)))
    params = (
        "task:\n"
        "  workingPath: '{}'\n"
        "  metas:\n"
        "    - variable-for-prompt: prompt\n"
        "    - variable-for-output: result\n"
        "    - timeout-sec: '30'\n"
        "  inputs:\n"
        "    - name: prompt\n"
        "      id: 1\n"
        "      dataType: variable\n"
        "  outputs:\n"
        "    - name: result\n"
        "      id: 2\n"
        "      dataType: variable\n"
    ).format(work)
    params_path = work / 'params.yaml'
    _write(params_path, params)
    return work, scripts, params_path


def _run(params_path):
    """(rc, stdout) of the real main(), captured into a utf-8 stream this test owns."""
    out = io.TextIOWrapper(io.BytesIO(), encoding='utf-8', newline='')
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        rc = mh_call_cc.main([str(params_path)])
    out.flush()
    return rc, out.buffer.getvalue().decode('utf-8')


def test_a_reported_mcp_outage_ends_the_function_with_a_negative_exit_code(tmp_path):
    work, scripts, params_path = _task(tmp_path, UNAVAILABLE_FAKE)

    rc, stdout = _run(params_path)

    assert (scripts / 'cc-argv.json').exists(), 'the fake CC was never called'
    assert rc == mh_call_cc.MCP_UNAVAILABLE_EXIT_CODE, stdout
    assert rc < 0, 'negative - not the 1 every ordinary failure returns'
    assert 'FAILED: Claude Code reported the MCP server unavailable - MCP_UNAVAILABLE: CONNECTION_CLOSED' in stdout
    assert not (work / 'artifacts' / '2').exists(), 'an outage must leave no output behind'


def test_ultracode_off_and_the_rule_reach_cc_as_files_by_bare_name(tmp_path):
    work, scripts, params_path = _task(tmp_path, UNAVAILABLE_FAKE)

    _run(params_path)

    argv = json.loads((scripts / 'cc-argv.json').read_text(encoding='utf-8'))
    assert argv[argv.index('--settings') + 1] == 'cc-settings.json'
    assert argv[argv.index('--append-system-prompt-file') + 1] == 'cc-system-prompt.txt'
    # the names are resolved against the task dir, CC's cwd - so the files must really be there
    assert json.loads((work / 'cc-settings.json').read_text(encoding='utf-8')) == {'ultracode': False}
    assert (work / 'cc-system-prompt.txt').read_text(encoding='utf-8') == mh_call_cc.MCP_UNAVAILABLE_RULE


def test_a_healthy_run_whose_console_echoes_the_rule_still_succeeds(tmp_path):
    work, scripts, params_path = _task(tmp_path, HEALTHY_FAKE)

    rc, stdout = _run(params_path)

    assert rc == 0, stdout
    assert (work / 'artifacts' / '2').read_text(encoding='utf-8') == 'the answer'
    # the echo really happened - without it this success would say nothing about the template line
    assert mh_call_cc.MCP_UNAVAILABLE_MARKER + ' ' + mh_call_cc.MCP_UNAVAILABLE_PLACEHOLDER in stdout
