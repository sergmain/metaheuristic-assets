# An integration test, requested: run mh.asset.call-cc's REAL main() with the `claude` CLI replaced by fake python
# scripts, and prove the failure path - which now runs `claude --version` for diagnosis - does NOT overwrite the
# main console log written from the actual CC call.
#
# This is deliberately NOT a unit test of the pure core (that is test_mh_call_cc.py, and MH-GIT-DELIVERY 5.5-5.6
# keeps main() out of it). Here the boundary IS the subject: two real subprocesses stand in for CC, so every file
# write and the version subprocess happen for real, and the console log on disk is read back afterwards. No doubles
# and no monkeypatching of production - a real fake `claude` executable that dispatches to two python scripts, which
# is exactly the shape a Processor runs the Function in.

import contextlib
import io
import os
import stat
import sys

import mh_call_cc

# --- the two scripts that replace CC -----------------------------------------------------------------------------

# 1) the CC call: drain the prompt on stdin, print a distinctive console (with a non-cp1252 char, the kind that
#    motivated utf8_console), leave a marker proving it ran, and FAIL so main() takes the version/diagnosis path.
#    Bytes via stdout.buffer: the fake's own stdout is a pipe, so text-mode would hit the very cp1252 crash the
#    Function guards against - not this test's subject.
CC_SCRIPT = (
    "import os, sys\n"
    "here = os.path.dirname(os.path.abspath(__file__))\n"
    "open(os.path.join(here, 'cc-ran'), 'w').close()\n"
    "sys.stdin.buffer.read()\n"
    "sys.stdout.buffer.write('CC-CONSOLE-MARKER: the real answer console\\n'.encode('utf-8'))\n"
    "sys.stdout.buffer.write('a non-cp1252 char \\u2192 here\\n'.encode('utf-8'))\n"
    "sys.stdout.buffer.flush()\n"
    "sys.exit(1)\n"
)

# 2) the `claude --version` call: print a distinctive version, leave a marker proving it ran, succeed.
VERSION_SCRIPT = (
    "import os, sys\n"
    "here = os.path.dirname(os.path.abspath(__file__))\n"
    "open(os.path.join(here, 'version-ran'), 'w').close()\n"
    "sys.stdout.write('claude 9.9.9-fake\\n')\n"
    "sys.exit(0)\n"
)

# glue: the ONE executable main() calls for BOTH invocations routes to whichever of the two scripts the args ask
# for. `claude --version` -> version script; the `--debug ...` CC call -> cc script.
ROUTER_SCRIPT = (
    "import os, runpy, sys\n"
    "here = os.path.dirname(os.path.abspath(__file__))\n"
    "target = 'fake_cc_version.py' if '--version' in sys.argv[1:] else 'fake_cc.py'\n"
    "runpy.run_path(os.path.join(here, target), run_name='__main__')\n"
)


def _write(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _fake_claude(scripts_dir):
    """A real executable that runs the router under this interpreter, the way a Processor runs `claude`."""
    _write(scripts_dir / 'fake_cc.py', CC_SCRIPT)
    _write(scripts_dir / 'fake_cc_version.py', VERSION_SCRIPT)
    router = scripts_dir / 'fake_claude.py'
    _write(router, ROUTER_SCRIPT)
    if os.name == 'nt':
        shim = scripts_dir / 'claude.cmd'
        _write(shim, '@"{}" "{}" %*\n'.format(sys.executable, router))
    else:
        shim = scripts_dir / 'claude'
        _write(shim, '#!/bin/sh\nexec "{}" "{}" "$@"\n'.format(sys.executable, router))
        os.chmod(shim, os.stat(shim).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return shim


def _task(work, scripts_dir):
    """A minimal but real task tree: working dir, the prompt input on disk, mh-env.yaml naming the fake claude.
    Single-quoted YAML scalars so a Windows path's backslashes stay literal."""
    (work / 'variable').mkdir(parents=True)
    _write(work / 'variable' / '1', 'derive requirements from this file')
    (work / 'artifacts').mkdir(parents=True)
    _write(work / 'artifacts' / 'mh-env.yaml', "envs:\n  claude-code: '{}'\n".format(_fake_claude(scripts_dir)))
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
    return params_path


def test_the_version_call_on_the_failure_path_does_not_overwrite_the_console_log(tmp_path):
    work = tmp_path / 'task'
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    params_path = _task(work, scripts)

    # capture into a utf-8 stream we own, so main()'s utf8_console(reconfigure) and the non-ascii console are
    # deterministic regardless of the platform code page - and so nothing here depends on pytest's capture shape
    out = io.TextIOWrapper(io.BytesIO(), encoding='utf-8', newline='')
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        rc = mh_call_cc.main([str(params_path)])
    out.flush()
    stdout = out.buffer.getvalue().decode('utf-8')

    console_log = (work / 'cc-data' / 'cc-console.log').read_text(encoding='utf-8')

    # the failure path ran to the end: CC really ran and failed, and the version call really executed - without
    # this second marker the no-overwrite result would be vacuous (the version branch might simply be skipped)
    assert rc == 1
    assert (scripts / 'cc-ran').exists(), 'the fake CC was never called'
    assert (scripts / 'version-ran').exists(), 'the version call never ran; a no-overwrite result would be vacuous'

    # THE POINT: the console log holds the CC console, whole, and the version output did not land in it
    assert 'CC-CONSOLE-MARKER: the real answer console' in console_log
    assert 'a non-cp1252 char \u2192 here' in console_log
    assert 'claude 9.9.9-fake' not in console_log, 'the --version output leaked into / overwrote the console log'

    # the version instead went to stdout, after the CC console - present in the run, kept apart from the log
    assert 'claude 9.9.9-fake' in stdout
    assert 'CC-CONSOLE-MARKER' in stdout
