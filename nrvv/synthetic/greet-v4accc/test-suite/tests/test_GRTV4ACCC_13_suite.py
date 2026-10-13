import os
import subprocess
import sys


def _run_program_without_input(tmp_path):
    env = dict(os.environ)
    result = subprocess.run(
        [sys.executable, "-m", "app"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(tmp_path),
        env=env,
        timeout=60,
        text=True,
    )
    return result.stdout, result.stderr


def test_greeting_is_written_to_standard_output(tmp_path):
    stdout, _stderr = _run_program_without_input(tmp_path)
    assert stdout.strip() != "", "standard output must contain the greeting"


def test_greeting_is_not_written_to_standard_error(tmp_path):
    stdout, stderr = _run_program_without_input(tmp_path)
    greeting_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    assert greeting_lines, "standard output must contain the greeting"
    for line in greeting_lines:
        assert line not in stderr, "greeting must not appear on standard error"


def test_standard_error_does_not_contain_greeting_text(tmp_path):
    stdout, stderr = _run_program_without_input(tmp_path)
    assert stdout.strip() != ""
    assert stdout.strip() not in stderr, "standard error must not contain the greeting"
