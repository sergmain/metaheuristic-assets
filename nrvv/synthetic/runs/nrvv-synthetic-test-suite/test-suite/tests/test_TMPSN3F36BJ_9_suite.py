import inspect

import nrvv_sample


def _get_class():
    cls = getattr(nrvv_sample, "NrvvSample", None)
    assert cls is not None, "module nrvv_sample must declare a class named 'NrvvSample'"
    assert inspect.isclass(cls), "'NrvvSample' must be a class"
    return cls


def test_class_declares_main_member():
    cls = _get_class()
    members = dict(inspect.getmembers(cls))
    assert "main" in members, "class NrvvSample must declare a member named 'main'"


def test_main_present_via_getattr():
    cls = _get_class()
    assert hasattr(cls, "main"), "class NrvvSample must have an attribute named 'main'"


def test_main_is_callable():
    cls = _get_class()
    main = getattr(cls, "main", None)
    assert main is not None, "'main' must be present on class NrvvSample"
    assert callable(main), "'main' must be callable (a method serving as entry point)"


def test_main_is_a_method_like_member():
    cls = _get_class()
    main = getattr(cls, "main")
    is_method_like = (
        inspect.isfunction(main)
        or inspect.ismethod(main)
        or isinstance(inspect.getattr_static(cls, "main"), (staticmethod, classmethod))
    )
    assert is_method_like, "'main' must be a method of class NrvvSample"


def test_main_in_class_dir():
    cls = _get_class()
    assert "main" in dir(cls), "'main' must appear among the declared members of class NrvvSample"
