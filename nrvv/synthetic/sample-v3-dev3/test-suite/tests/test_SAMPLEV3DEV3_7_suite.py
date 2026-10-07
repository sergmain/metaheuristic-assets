import io
import sys

import pytest

import nrvv_sample


def _entry_point():
    """Return a zero-argument callable for the program's sole launch point.

    The Java source defines a single class ``NrvvSample`` with a parameterless
    ``main()`` method; the port keeps the class name and snake_cases the method
    (``main`` stays ``main``). An instance is created with no arguments.
    """
    cls = getattr(nrvv_sample, "NrvvSample")
    instance = cls()
    main = getattr(instance, "main")
    return main


def test_entry_point_is_present_and_callable():
    main = _entry_point()
    assert callable(main)


def test_launch_without_arguments_runs_to_completion(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["nrvv_sample"])
    main = _entry_point()
    # Must run to normal completion: no missing-entry-point / missing-argument error.
    result = main()
    # A parameterless entry point returns normally (typically None).
    assert result is None or result == 0


def test_launch_takes_no_command_line_arguments(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["nrvv_sample"])
    main = _entry_point()
    # Invoking with exactly zero extra positional arguments must succeed.
    main()


def test_launch_does_not_prompt_or_wait_for_input(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["nrvv_sample"])
    # Empty stdin: any attempt to read input returns EOF immediately rather
    # than blocking, and a prompt via input() would raise EOFError.
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    main = _entry_point()
    try:
        main()
    except EOFError:
        pytest.fail("entry point prompted for / waited on input")


def test_second_invocation_behaves_identically(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["nrvv_sample"])

    main_first = _entry_point()
    main_first()
    first = capsys.readouterr()

    main_second = _entry_point()
    main_second()
    second = capsys.readouterr()

    # Sole launch point, no arguments or input: repeated launches match.
    assert first.out == second.out
    assert first.err == second.err


def test_repeated_invocations_never_error(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["nrvv_sample"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    for _ in range(3):
        _entry_point()()
