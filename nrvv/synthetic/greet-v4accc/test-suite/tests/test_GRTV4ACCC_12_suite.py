import nrvv_sample


def _capture_greeting(capsys):
    cls = nrvv_sample.NrvvSample
    cls().main()
    return capsys.readouterr().out


def test_greeting_produces_non_empty_text_output(capsys):
    out = _capture_greeting(capsys)
    assert isinstance(out, str)
    assert out.strip() != ""


def test_greeting_output_ends_with_line_ending(capsys):
    out = _capture_greeting(capsys)
    assert out.endswith("\n")


def test_greeting_output_has_no_trailing_spaces_before_line_ending(capsys):
    out = _capture_greeting(capsys)
    for line in out.split("\n")[:-1]:
        assert line == line.rstrip(" \t")


def test_greeting_output_is_plain_single_line_text(capsys):
    out = _capture_greeting(capsys)
    assert out.count("\n") == 1
    assert "\r" not in out
