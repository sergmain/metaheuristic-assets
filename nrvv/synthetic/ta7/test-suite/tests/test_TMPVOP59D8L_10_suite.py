import inspect

import pytest

import nrvv_sample


def _get_main():
    """Locate the callable 'main' entry point.

    Prefer NrvvSample.main invoked on a no-arg instance; fall back to a
    module-level main if the port exposes it that way.
    """
    cls = getattr(nrvv_sample, "NrvvSample", None)
    if cls is not None and hasattr(cls, "main"):
        instance = cls()
        return getattr(instance, "main")
    return getattr(nrvv_sample, "main")


def test_main_exists_on_class():
    cls = getattr(nrvv_sample, "NrvvSample", None)
    assert cls is not None, "NrvvSample class must exist"
    assert hasattr(cls, "main"), "NrvvSample must define a 'main' method"


def test_main_is_callable():
    main = _get_main()
    assert callable(main), "'main' must be callable"


def test_main_takes_no_arguments():
    main = _get_main()
    sig = inspect.signature(main)
    required = [
        p
        for p in sig.parameters.values()
        if p.default is inspect.Parameter.empty
        and p.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    ]
    assert required == [], "'main' must be invocable with no arguments"


def test_main_invokes_with_no_arguments():
    main = _get_main()
    # Must complete without raising when called with no arguments.
    main()


def test_main_returns_no_value():
    main = _get_main()
    result = main()
    assert result is None, "'main' returns void (None) as the entry point"
