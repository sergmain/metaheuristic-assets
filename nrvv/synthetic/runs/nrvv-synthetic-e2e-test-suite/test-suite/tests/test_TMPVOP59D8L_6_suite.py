import inspect

import nrvv_sample


def _get_class():
    assert hasattr(nrvv_sample, "NrvvSample"), "module must declare class NrvvSample"
    cls = getattr(nrvv_sample, "NrvvSample")
    assert inspect.isclass(cls), "NrvvSample must be a class"
    return cls


def test_class_declares_main_method():
    cls = _get_class()
    assert "main" in dir(cls), "NrvvSample must declare a method named 'main'"
    assert callable(getattr(cls, "main")), "'main' must be callable"


def test_main_accepts_no_parameters():
    cls = _get_class()
    instance = cls()
    sig = inspect.signature(instance.main)
    assert list(sig.parameters) == [], (
        "main must declare an empty parameter list (no parameters besides the "
        "implicit instance), found: %r" % list(sig.parameters)
    )


def test_main_defined_as_instance_method_with_only_self():
    cls = _get_class()
    func = inspect.unwrap(cls.__dict__["main"])
    params = list(inspect.signature(func).parameters)
    assert params == ["self"], (
        "unbound main should accept only the implicit instance parameter, "
        "found: %r" % params
    )


def test_main_returns_void():
    cls = _get_class()
    instance = cls()
    result = instance.main()
    assert result is None, (
        "main must return void (None in Python), returned: %r" % (result,)
    )


def test_main_return_annotation_is_void_if_present():
    cls = _get_class()
    sig = inspect.signature(cls.main)
    annotation = sig.return_annotation
    if annotation is inspect.Signature.empty:
        return
    assert annotation in (None, type(None), "None"), (
        "main return type annotation must denote void, found: %r" % (annotation,)
    )
