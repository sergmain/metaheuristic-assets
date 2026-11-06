import nrvv_sample

EXPECTED = "Hello, NRVV"


def _run(capsys):
    """Execute the ported program with no input and return captured stdout."""
    instance = nrvv_sample.NrvvSample()
    instance.main()
    return capsys.readouterr().out


def test_stripped_output_is_exact_greeting(capsys):
    out = _run(capsys)
    assert out.rstrip("\r\n") == EXPECTED


def test_output_is_greeting_optionally_newline_terminated(capsys):
    out = _run(capsys)
    assert out in (EXPECTED, EXPECTED + "\n", EXPECTED + "\r\n")


def test_output_has_no_extra_content(capsys):
    out = _run(capsys)
    # Nothing other than the greeting and at most one trailing terminator.
    assert out.startswith(EXPECTED)
    trailing = out[len(EXPECTED):]
    assert trailing in ("", "\n", "\r\n")


def test_output_is_single_line(capsys):
    out = _run(capsys)
    lines = out.splitlines()
    assert lines == [EXPECTED]


def test_greeting_text_present_and_only_once(capsys):
    out = _run(capsys)
    assert EXPECTED in out
    assert out.count(EXPECTED) == 1
