import nrvv_sample


def _make_instance():
    cls = getattr(nrvv_sample, "NrvvSample")
    return cls()


def test_nrvvsample_class_exists():
    assert hasattr(nrvv_sample, "NrvvSample")
    assert isinstance(getattr(nrvv_sample, "NrvvSample"), type)


def test_main_method_exists_and_callable():
    instance = _make_instance()
    assert hasattr(instance, "main")
    assert callable(getattr(instance, "main"))


def test_main_takes_no_arguments():
    instance = _make_instance()
    # Should be invocable with no arguments beyond the bound instance.
    result = instance.main()
    assert result is None


def test_main_returns_void_equivalent():
    instance = _make_instance()
    result = instance.main()
    assert result is None


def test_main_runs_to_completion_without_error(capsys):
    instance = _make_instance()
    # Invoking as the program's entry point must complete without raising.
    instance.main()
    # capsys captures any standard output produced; no exception means success.
    capsys.readouterr()


def test_main_invokable_repeatedly_without_error():
    instance = _make_instance()
    instance.main()
    instance.main()
