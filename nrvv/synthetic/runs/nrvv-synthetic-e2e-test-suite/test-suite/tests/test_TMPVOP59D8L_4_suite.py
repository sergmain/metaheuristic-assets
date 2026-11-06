import importlib
import inspect

import pytest

EXPECTED = "Hello, NRVV\n"


def _import_module():
    return importlib.import_module("nrvv_sample")


def _resolve_main_callable():
    """Return a zero-argument callable for the program's main entry point.

    The source is NrvvSample.java whose body is a `main` method. The port keeps
    the class name NrvvSample and spells the method `main`. We accept the entry
    point as a module-level function, a static/class method, or an instance
    method invoked on an instance built with no arguments.
    """
    mod = _import_module()

    # Prefer a class named NrvvSample with a `main` method.
    cls = getattr(mod, "NrvvSample", None)
    if cls is not None and hasattr(cls, "main"):
        attr = inspect.getattr_static(cls, "main")
        if isinstance(attr, (staticmethod, classmethod)):
            return getattr(cls, "main")
        # Plain function => instance method; build instance with no args.
        return getattr(cls(), "main")

    # Fall back to a module-level `main` function.
    if hasattr(mod, "main"):
        return getattr(mod, "main")

    raise AssertionError("No 'main' entry point found in module 'nrvv_sample'")


def _run_main(capsys):
    main = _resolve_main_callable()
    main()
    return capsys.readouterr()


def test_stdout_is_exactly_the_greeting_line(capsys):
    captured = _run_main(capsys)
    assert captured.out == EXPECTED


def test_no_extra_stdout_beyond_single_line(capsys):
    captured = _run_main(capsys)
    assert captured.out.splitlines() == ["Hello, NRVV"]


def test_stdout_ends_with_line_terminator(capsys):
    captured = _run_main(capsys)
    assert captured.out.endswith("\n")
    assert captured.out.count("\n") == 1


def test_greeting_text_matches_exactly(capsys):
    captured = _run_main(capsys)
    assert captured.out.rstrip("\n") == "Hello, NRVV"
