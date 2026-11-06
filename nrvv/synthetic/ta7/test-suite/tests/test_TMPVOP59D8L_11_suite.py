import nrvv_sample


def _invoke_main():
    if hasattr(nrvv_sample, "main"):
        return nrvv_sample.main()
    for name in dir(nrvv_sample):
        obj = getattr(nrvv_sample, name)
        if isinstance(obj, type) and hasattr(obj, "main"):
            method = getattr(obj, "main")
            try:
                return method()
            except TypeError:
                return method(obj())
    raise AssertionError("No main entry point found in nrvv_sample")


def test_main_prints_expected_line(capsys):
    _invoke_main()
    out = capsys.readouterr().out
    assert out == "Hello, NRVV\n"


def test_main_output_is_single_line(capsys):
    _invoke_main()
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines == ["Hello, NRVV"]


def test_main_output_ends_with_line_terminator(capsys):
    _invoke_main()
    out = capsys.readouterr().out
    assert out.endswith("\n")
    assert out.count("\n") == 1


def test_main_content_exact(capsys):
    _invoke_main()
    out = capsys.readouterr().out
    assert out.rstrip("\n") == "Hello, NRVV"


def test_main_no_extra_output(capsys):
    _invoke_main()
    captured = capsys.readouterr()
    assert captured.out == "Hello, NRVV\n"
