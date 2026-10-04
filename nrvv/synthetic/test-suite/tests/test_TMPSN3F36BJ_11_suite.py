import importlib
import inspect

import pytest

MODULE_NAME = "nrvv_sample"
CLASS_NAME = "NrvvSample"


def _import_module():
    """Import the ported module. Equivalent to the Java source compiling cleanly."""
    return importlib.import_module(MODULE_NAME)


def _make_instance():
    mod = _import_module()
    cls = getattr(mod, CLASS_NAME)
    return cls()


def _resolve_main():
    """Locate the ported `main` entry point, on an instance or on the module."""
    mod = _import_module()
    cls = getattr(mod, CLASS_NAME, None)
    if cls is not None:
        inst = cls()
        if hasattr(inst, "main"):
            return getattr(inst, "main")
    if hasattr(mod, "main"):
        return getattr(mod, "main")
    raise AssertionError("no `main` entry point found on class or module")


def _required_positional_count(fn):
    sig = inspect.signature(fn)
    count = 0
    for p in sig.parameters.values():
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                      inspect.Parameter.POSITIONAL_OR_KEYWORD) \
                and p.default is inspect.Parameter.empty:
            count += 1
    return count


def _invoke_main(fn):
    """Run main, mirroring Java's `main(String[] args)` with an empty arg list
    when the port declares a required positional parameter."""
    if _required_positional_count(fn) >= 1:
        return fn([])
    return fn()


def test_module_imports_cleanly():
    # Successful compilation analogue: the ported module imports without error.
    assert _import_module() is not None


def test_class_is_present():
    mod = _import_module()
    assert hasattr(mod, CLASS_NAME), "ported class NrvvSample must exist"


def test_instance_constructs_without_arguments():
    inst = _make_instance()
    assert inst is not None


def test_main_entry_point_is_callable():
    main = _resolve_main()
    assert callable(main)


def test_main_runs_to_normal_termination():
    # Running the program analogue: main executes without raising.
    main = _resolve_main()
    try:
        _invoke_main(main)
    except SystemExit as exc:
        # Normal termination may surface as an exit; code 0/None is success.
        assert exc.code in (0, None), f"program terminated abnormally: {exc.code}"
    except Exception as exc:  # pragma: no cover - failure path
        pytest.fail(f"runtime error during execution: {exc!r}")


def test_main_runs_repeatably_without_error():
    for _ in range(2):
        main = _resolve_main()
        try:
            _invoke_main(main)
        except SystemExit as exc:
            assert exc.code in (0, None), f"program terminated abnormally: {exc.code}"
        except Exception as exc:  # pragma: no cover - failure path
            pytest.fail(f"runtime error during execution: {exc!r}")
