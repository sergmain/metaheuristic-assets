import nrvv_sample


def _invoke_main(obj):
    """Invoke the ported main entry point and return True if a callable was found."""
    # Primary: instance method `main` on an instance created with no arguments.
    cls = getattr(nrvv_sample, "NrvvSample", None)
    if cls is not None:
        instance = cls()
        main = getattr(instance, "main", None)
        if callable(main):
            main()
            return True
        # Fall back to a class-level/static `main`.
        cmain = getattr(cls, "main", None)
        if callable(cmain):
            cmain()
            return True
    # Fall back to a module-level `main`.
    mmain = getattr(nrvv_sample, "main", None)
    if callable(mmain):
        mmain()
        return True
    raise AssertionError("No main entry point found on nrvv_sample")


def test_main_prints_hello_nrvv_line(capsys):
    _invoke_main(nrvv_sample)
    out = capsys.readouterr().out
    assert "Hello, NRVV\n" in out


def test_main_output_is_exactly_the_greeting_line(capsys):
    _invoke_main(nrvv_sample)
    out = capsys.readouterr().out
    assert out == "Hello, NRVV\n"


def test_main_output_ends_with_line_terminator(capsys):
    _invoke_main(nrvv_sample)
    out = capsys.readouterr().out
    assert out.endswith("\n")


def test_greeting_line_has_no_other_text(capsys):
    _invoke_main(nrvv_sample)
    out = capsys.readouterr().out
    lines = out.split("\n")
    # Exactly one non-empty line, equal to the greeting, with nothing else on it.
    non_empty = [ln for ln in lines if ln != ""]
    assert non_empty == ["Hello, NRVV"]


def test_main_prints_single_line(capsys):
    _invoke_main(nrvv_sample)
    out = capsys.readouterr().out
    # One greeting followed by a terminator produces exactly one trailing empty split field.
    assert out.count("\n") == 1
    assert out.splitlines() == ["Hello, NRVV"]
