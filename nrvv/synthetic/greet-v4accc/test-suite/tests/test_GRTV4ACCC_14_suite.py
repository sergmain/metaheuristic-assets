import io
import sys

import nrvv_sample


def _run_program(monkeypatch):
    monkeypatch.setattr(sys, 'stdin', io.StringIO(''))
    if hasattr(nrvv_sample, 'main'):
        nrvv_sample.main()
    else:
        nrvv_sample.NrvvSample().main()


def test_output_ends_with_line_break(monkeypatch, capsys):
    _run_program(monkeypatch)
    out = capsys.readouterr().out
    assert out.endswith('\n')


def test_output_is_exactly_one_line(monkeypatch, capsys):
    _run_program(monkeypatch)
    out = capsys.readouterr().out
    assert out.count('\n') == 1
    assert len(out.splitlines()) == 1


def test_no_blank_lines_or_surrounding_text(monkeypatch, capsys):
    _run_program(monkeypatch)
    out = capsys.readouterr().out
    line = out[:-1]
    assert line != ''
    assert '\r' not in out
    assert out == line + '\n'


def test_no_leading_or_trailing_spaces(monkeypatch, capsys):
    _run_program(monkeypatch)
    out = capsys.readouterr().out
    line = out[:-1]
    assert line == line.strip()
