import subprocess
import sys


def test_main_is_defined_on_class():
    import nrvv_sample

    assert callable(getattr(nrvv_sample.NrvvSample, 'main', None))


def test_main_runs_with_no_arguments_and_prints_one_line(capsys):
    import nrvv_sample

    capsys.readouterr()
    nrvv_sample.NrvvSample().main()
    out = capsys.readouterr().out
    assert out.strip() != ''
    assert len(out.splitlines()) == 1


def test_main_completes_normally_returning_none(capsys):
    import nrvv_sample

    capsys.readouterr()
    result = nrvv_sample.NrvvSample().main()
    capsys.readouterr()
    assert result is None


def test_running_module_as_program_prints_greeting_once(tmp_path, capsys):
    import nrvv_sample

    capsys.readouterr()
    proc = subprocess.run(
        [sys.executable, '-m', 'nrvv_sample'],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0
    nrvv_sample.NrvvSample().main()
    expected = capsys.readouterr().out
    assert proc.stdout == expected
    assert len(proc.stdout.splitlines()) == 1
