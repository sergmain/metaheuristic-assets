import io
import subprocess
import sys

import nrvv_sample

EXPECTED = "Hello, NRVV\n"


def _run_main():
    main = getattr(nrvv_sample, "main", None)
    if main is None:
        main = nrvv_sample.NrvvSample().main
    main()


def test_main_prints_exact_greeting(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    _run_main()
    assert capsys.readouterr().out == EXPECTED


def test_main_completes_without_stderr_output(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    _run_main()
    assert capsys.readouterr().err == ""


def test_script_run_prints_exact_greeting_and_exits_zero(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "nrvv_sample"],
        input="",
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=60,
    )
    assert result.returncode == 0
    assert result.stdout == EXPECTED
    assert result.stderr == ""
