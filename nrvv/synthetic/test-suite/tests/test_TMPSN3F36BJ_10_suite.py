import importlib
import inspect


def _get_module():
    return importlib.import_module("nrvv_sample")


def test_module_importable():
    module = _get_module()
    assert module is not None


def test_nrvv_sample_class_exists():
    module = _get_module()
    assert hasattr(module, "NrvvSample"), "module nrvv_sample has no attribute 'NrvvSample'"


def test_nrvv_sample_is_a_class():
    module = _get_module()
    obj = getattr(module, "NrvvSample", None)
    assert inspect.isclass(obj), "'NrvvSample' is defined but is not a class"


def test_nrvv_sample_name_is_exact():
    module = _get_module()
    obj = getattr(module, "NrvvSample", None)
    assert inspect.isclass(obj)
    assert obj.__name__ == "NrvvSample", "class name is not exactly 'NrvvSample'"


def test_nrvv_sample_is_public():
    module = _get_module()
    obj = getattr(module, "NrvvSample", None)
    assert inspect.isclass(obj)
    # In Python, a public class/identifier is one that does not begin with an
    # underscore (name-mangled/private convention).
    assert not obj.__name__.startswith("_"), "class 'NrvvSample' is not public"


def test_nrvv_sample_present_in_class_members():
    module = _get_module()
    class_names = [name for name, value in inspect.getmembers(module, inspect.isclass)
                   if value.__module__ == module.__name__]
    assert "NrvvSample" in class_names, (
        "no public class named exactly 'NrvvSample' is defined in the module"
    )
