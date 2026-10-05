import inspect

import pytest


def test_module_importable():
    import nrvv_sample
    assert nrvv_sample is not None


def test_nrvvsample_class_exists():
    import nrvv_sample
    assert hasattr(nrvv_sample, "NrvvSample"), (
        "module nrvv_sample must provide a class named NrvvSample"
    )


def test_nrvvsample_is_a_class():
    import nrvv_sample
    assert inspect.isclass(nrvv_sample.NrvvSample), (
        "NrvvSample must be a class"
    )


def test_nrvvsample_named_exactly():
    import nrvv_sample
    assert nrvv_sample.NrvvSample.__name__ == "NrvvSample", (
        "the class must be named exactly 'NrvvSample'"
    )


def test_nrvvsample_instantiable_with_no_arguments():
    import nrvv_sample
    instance = nrvv_sample.NrvvSample()
    assert isinstance(instance, nrvv_sample.NrvvSample)


def test_no_differently_named_class_substituted():
    import nrvv_sample
    cls = getattr(nrvv_sample, "NrvvSample", None)
    assert cls is not None
    assert inspect.isclass(cls)
    assert cls.__name__ == "NrvvSample"
