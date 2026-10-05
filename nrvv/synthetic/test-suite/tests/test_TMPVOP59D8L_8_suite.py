import importlib
import inspect

import pytest


def test_module_imports():
    module = importlib.import_module("nrvv_sample")
    assert module is not None


def test_nrvv_sample_name_resolves():
    module = importlib.import_module("nrvv_sample")
    assert hasattr(module, "NrvvSample"), "public name 'NrvvSample' must be resolvable from the module"
    unit = getattr(module, "NrvvSample")
    assert unit is not None


def test_nrvv_sample_is_a_class():
    module = importlib.import_module("nrvv_sample")
    unit = getattr(module, "NrvvSample")
    assert inspect.isclass(unit), "NrvvSample must be a class/type"


def test_nrvv_sample_has_exact_name():
    module = importlib.import_module("nrvv_sample")
    unit = getattr(module, "NrvvSample")
    assert unit.__name__ == "NrvvSample"


def test_nrvv_sample_is_single_defined_unit():
    module = importlib.import_module("nrvv_sample")
    first = getattr(module, "NrvvSample")
    second = getattr(module, "NrvvSample")
    assert first is second, "resolving the name must yield one single defined unit"
