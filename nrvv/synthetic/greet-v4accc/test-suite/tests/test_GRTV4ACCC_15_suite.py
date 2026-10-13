import importlib
import io
import runpy
import sys


def _captured_output(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    runpy.run_module("app", run_name="__main__")
    out = capsys.readouterr().out
    if not out:
        app = importlib.import_module("app")
        main = getattr(app, "main", None)
        if callable(main):
            main()
            out = capsys.readouterr().out
    return out


def test_program_output_is_non_empty(monkeypatch, capsys):
    out = _captured_output(monkeypatch, capsys)
    assert out != ""


def test_program_output_ends_with_line_feed(monkeypatch, capsys):
    out = _captured_output(monkeypatch, capsys)
    assert out != ""
    assert out[-1] == "\n"
