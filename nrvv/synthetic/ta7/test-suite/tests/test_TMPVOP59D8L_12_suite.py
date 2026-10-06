import inspect

import nrvv_sample


def test_nrvvsample_attribute_exists():
    assert hasattr(nrvv_sample, "NrvvSample"), \
        "module nrvv_sample must define a public unit named NrvvSample"


def test_nrvvsample_is_a_class():
    obj = getattr(nrvv_sample, "NrvvSample")
    assert inspect.isclass(obj), "NrvvSample must be a class"


def test_nrvvsample_named_exactly():
    cls = getattr(nrvv_sample, "NrvvSample")
    assert cls.__name__ == "NrvvSample", \
        "the class must be accessible under exactly the name NrvvSample"


def test_nrvvsample_can_be_instantiated():
    cls = getattr(nrvv_sample, "NrvvSample")
    instance = cls()
    assert instance is not None, "instantiating NrvvSample() must yield an instance"


def test_nrvvsample_instance_is_of_class():
    cls = getattr(nrvv_sample, "NrvvSample")
    instance = cls()
    assert isinstance(instance, cls), \
        "NrvvSample() must produce an instance of NrvvSample"
