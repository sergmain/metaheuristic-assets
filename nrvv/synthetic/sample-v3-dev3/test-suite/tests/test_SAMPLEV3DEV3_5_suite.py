import nrvv_sample


def _run_program(capsys):
    """Invoke the ported program's entry point and return its captured stdout."""
    cls = getattr(nrvv_sample, "NrvvSample", None)
    if cls is not None and hasattr(cls, "main"):
        cls().main()
    elif hasattr(nrvv_sample, "main"):
        nrvv_sample.main()
    else:
        raise AssertionError("no runnable entry point found in nrvv_sample")
    return capsys.readouterr().out


def test_output_ends_with_newline(capsys):
    out = _run_program(capsys)
    assert out.endswith("\n")


def test_output_has_a_non_empty_message_before_the_separator(capsys):
    out = _run_program(capsys)
    # There must be an actual greeting, not just a bare newline.
    assert out.rstrip("\r\n") != ""


def test_message_stands_as_a_single_terminated_line(capsys):
    out = _run_program(capsys)
    lines = out.splitlines(keepends=True)
    assert lines, "expected at least one line of output"
    # The greeting occupies its own complete, newline-terminated line.
    assert lines[-1].endswith("\n")


def test_no_characters_trail_after_the_final_separator(capsys):
    out = _run_program(capsys)
    # Nothing may follow the terminating line separator on that same line.
    assert out[-1] == "\n"
    assert out.split("\n")[-1] == ""
