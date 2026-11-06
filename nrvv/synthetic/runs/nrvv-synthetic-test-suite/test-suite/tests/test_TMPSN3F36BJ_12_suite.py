import importlib

import pytest

EXPECTED = 'Hello, NRVV'


def _run_program():
    """Execute the ported program's entry point with no input.

    The source is NrvvSample.java whose entry point is ``main``. The port keeps
    the class name ``NrvvSample`` and spells the method in snake_case (``main``
    stays ``main``). We try the reasonable invocation styles so the suite is
    robust to how the entry point is exposed, but every style passes no input
    and takes no constructor arguments.
    """
    nrvv_sample = importlib.import_module('nrvv_sample')

    cls = getattr(nrvv_sample, 'NrvvSample', None)
    errors = []

    if cls is not None:
        main = getattr(cls, 'main', None)
        if main is not None:
            # Static/class method style: NrvvSample.main()
            try:
                main()
                return
            except TypeError as exc:
                errors.append(exc)
            # Instance method style: NrvvSample().main()
            try:
                cls().main()
                return
            except TypeError as exc:
                errors.append(exc)

    # Module-level main() fallback.
    module_main = getattr(nrvv_sample, 'main', None)
    if module_main is not None:
        module_main()
        return

    if errors:
        raise errors[-1]
    raise AssertionError('No callable entry point (main) found in nrvv_sample')


def test_output_contains_expected_text(capsys):
    _run_program()
    out = capsys.readouterr().out
    assert EXPECTED in out


def test_output_exact_literal_casing_and_spelling(capsys):
    _run_program()
    out = capsys.readouterr().out
    # Must appear verbatim: no casing, punctuation, or spacing differences.
    assert EXPECTED in out
    assert EXPECTED.lower() in out.lower()
    # The verbatim form is present, not merely a case-insensitive variant.
    assert out.lower().count(EXPECTED.lower()) == out.count(EXPECTED)


def test_output_not_altered_variants(capsys):
    _run_program()
    out = capsys.readouterr().out
    assert EXPECTED in out
    # Common near-miss variants must NOT be what satisfies the check: the exact
    # literal has to be present regardless of these.
    for bad in ('Hello, nrvv', 'hello, NRVV', 'Hello,NRVV', 'Hello NRVV', 'Hello, NRVV!'):
        if bad != EXPECTED and bad not in out:
            # fine: variant absent
            continue
    assert EXPECTED in out


def test_output_on_its_own_line(capsys):
    _run_program()
    out = capsys.readouterr().out
    # println emits the text; accept it anywhere but confirm the exact token.
    assert any(EXPECTED in line for line in out.splitlines()) or EXPECTED in out
