import os
import sys
import importlib

import pytest


def _entry_point():
    """Return a zero-argument callable that is the program's single entry point.

    The port keeps the source class name ``NrvvSample`` and spells the method
    ``main`` in snake_case (still ``main``). The instance is created with no
    arguments, per the porting rules.
    """
    module = importlib.import_module("nrvv_sample")
    cls = getattr(module, "NrvvSample", None)
    if cls is not None and hasattr(cls, "main"):
        instance = cls()
        return instance.main
    # Fallbacks in case the entry point is exposed differently.
    if hasattr(module, "main"):
        return getattr(module, "main")
    raise AssertionError("no callable entry point 'main' found on nrvv_sample")


def _snapshot_tree(root):
    paths = set()
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames:
            paths.add(os.path.join(dirpath, name))
        for name in filenames:
            paths.add(os.path.join(dirpath, name))
    return paths


def test_runs_to_completion_without_error(capsys):
    entry = _entry_point()
    entry()  # must not raise
    capsys.readouterr()


def test_yields_no_return_value(capsys):
    entry = _entry_point()
    result = entry()
    capsys.readouterr()
    assert result is None


def test_produces_console_output(capsys):
    entry = _entry_point()
    entry()
    captured = capsys.readouterr()
    assert captured.out != ""


def test_console_output_is_sole_stream_used(capsys):
    entry = _entry_point()
    entry()
    captured = capsys.readouterr()
    # The observable effect is console output on stdout; nothing on stderr.
    assert captured.err == ""
    assert captured.out != ""


def test_creates_no_files(tmp_path, capsys):
    work = tmp_path / "work"
    work.mkdir()
    before = _snapshot_tree(str(work))
    old_cwd = os.getcwd()
    os.chdir(str(work))
    try:
        entry = _entry_point()
        entry()
    finally:
        os.chdir(old_cwd)
    capsys.readouterr()
    after = _snapshot_tree(str(work))
    assert after == before


def test_repeated_invocation_has_no_persisted_side_effect(tmp_path, capsys):
    work = tmp_path / "repeat"
    work.mkdir()
    old_cwd = os.getcwd()
    os.chdir(str(work))
    outputs = []
    try:
        for _ in range(2):
            entry = _entry_point()
            result = entry()
            assert result is None
            outputs.append(capsys.readouterr().out)
    finally:
        os.chdir(old_cwd)
    # No files left behind by any run.
    assert _snapshot_tree(str(work)) == set()
    # Pure console behaviour: each run still produced output.
    assert all(text != "" for text in outputs)


def test_requires_only_standard_runtime(capsys):
    # Importing the module must succeed using only what is already available;
    # no optional/third-party component is pulled in to run the entry point.
    module = importlib.import_module("nrvv_sample")
    assert module is not None
    entry = _entry_point()
    entry()
    capsys.readouterr()


def test_entry_point_takes_no_arguments(capsys):
    # A self-contained, parameterless entry point: callable with no arguments.
    entry = _entry_point()
    assert callable(entry)
    entry()
    capsys.readouterr()
