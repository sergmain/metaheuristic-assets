# The decision-14 launcher against a synthetic suite built in tmp_path: a target module, tests that import it, and
# .suite files listing node ids. Each test runs the real pytest through the launcher and asserts the verdict.

import os

import pytest

import nrvv_suite_run as sr
from conftest import write

TARGET = {'greeter.py': "def greet(name):\n    return 'Hello, ' + name\n"}

TESTS = {
    'tests/__init__.py': '',
    'tests/test_greeter.py':
        'from greeter import greet\n\n'
        'def test_greets():\n    assert greet("Ann") == "Hello, Ann"\n\n'
        'def test_greets_empty():\n    assert greet("") == "Hello, "\n',
    'tests/test_broken.py':
        'from greeter import greet\n\n'
        'def test_wrong():\n    assert greet("Ann") == "Hi, Ann"\n',
    'tests/test_skipped.py':
        'import pytest\n\n'
        '@pytest.mark.skip(reason="not today")\n'
        'def test_later():\n    assert True\n',
    'tests/test_empty.py': '# no tests here\n',
    'tests/test_class.py':
        'class TestGreeter:\n    def test_inside(self):\n        assert True\n',
}


@pytest.fixture
def dirs(tmp_path):
    ts = str(tmp_path / 'test-suite')
    tg = str(tmp_path / 'target')
    out = str(tmp_path / 'verification')
    write(tg, TARGET)
    write(ts, TESTS)
    return ts, tg, out


def suite(ts, name, *lines):
    write(ts, {'suites/' + name + '.suite': '\n'.join(lines) + '\n'})


def test_a_suite_whose_listed_tests_pass_is_pass(dirs):
    ts, tg, out = dirs
    suite(ts, 'REQ_1_suite', '# greeting', '', 'tests/test_greeter.py::test_greets',
          'tests/test_greeter.py::test_greets_empty')

    e = sr.run_suite(ts, 'REQ_1_suite', tg, out)

    assert e['verdict'] == 'PASS'
    assert e['exitCode'] == 0
    assert e['missingIds'] == []
    assert e['listedIds'] == ['tests/test_greeter.py::test_greets', 'tests/test_greeter.py::test_greets_empty']
    assert [t['outcome'] for t in e['tests']] == ['PASS', 'PASS']
    assert e['xml'] == os.path.join(out, 'REQ_1_suite.xml') and os.path.isfile(e['xml'])


def test_a_listed_id_that_does_not_exist_is_error(dirs):
    ts, tg, out = dirs
    suite(ts, 'REQ_2_suite', 'tests/test_greeter.py::test_greets', 'tests/test_greeter.py::test_nope')

    e = sr.run_suite(ts, 'REQ_2_suite', tg, out)

    assert e['verdict'] == 'ERROR'
    assert 'tests/test_greeter.py::test_nope' in e['missingIds']


def test_pytest_exit_5_nothing_collected_is_error(dirs):
    ts, tg, out = dirs
    suite(ts, 'REQ_3_suite', 'tests/test_empty.py')

    e = sr.run_suite(ts, 'REQ_3_suite', tg, out)

    assert e['exitCode'] == 5
    assert e['verdict'] == 'ERROR'
    assert e['missingIds'] == ['tests/test_empty.py']


def test_a_failing_listed_test_is_fail(dirs):
    ts, tg, out = dirs
    suite(ts, 'REQ_4_suite', 'tests/test_greeter.py::test_greets', 'tests/test_broken.py::test_wrong')

    e = sr.run_suite(ts, 'REQ_4_suite', tg, out)

    assert e['verdict'] == 'FAIL'
    assert e['exitCode'] == 1
    assert [t['outcome'] for t in e['tests']] == ['PASS', 'FAIL']
    assert e['tests'][1]['message']


def test_a_skipped_listed_test_did_not_run_and_is_error(dirs):
    ts, tg, out = dirs
    suite(ts, 'REQ_5_suite', 'tests/test_skipped.py::test_later')

    e = sr.run_suite(ts, 'REQ_5_suite', tg, out)

    assert e['verdict'] == 'ERROR'
    assert e['missingIds'] == ['tests/test_skipped.py::test_later']


def test_a_suite_listing_nothing_is_error_and_pytest_is_not_run(dirs):
    ts, tg, out = dirs
    suite(ts, 'REQ_6_suite', '# only a comment')

    e = sr.run_suite(ts, 'REQ_6_suite', tg, out)

    assert e['verdict'] == 'ERROR'
    assert e['exitCode'] is None
    assert e['xml'] is None


def test_a_listed_file_or_class_covers_the_tests_under_it(dirs):
    ts, tg, out = dirs
    suite(ts, 'REQ_7_suite', 'tests/test_greeter.py', 'tests/test_class.py::TestGreeter')

    e = sr.run_suite(ts, 'REQ_7_suite', tg, out)

    assert e['verdict'] == 'PASS'
    assert e['missingIds'] == []


def test_run_suites_runs_every_suite_file_in_name_order(dirs):
    ts, tg, out = dirs
    suite(ts, 'REQ_9_suite', 'tests/test_greeter.py::test_greets')
    suite(ts, 'REQ_10_suite', 'tests/test_broken.py::test_wrong')

    report = sr.run_suites(ts, tg, out)

    assert [(e['suite'], e['verdict']) for e in report] == [('REQ_10_suite', 'FAIL'), ('REQ_9_suite', 'PASS')]


def test_an_invalid_suite_name_is_refused(dirs):
    ts, tg, out = dirs
    with pytest.raises(ValueError):
        sr.run_suite(ts, 'REQ__1_suite', tg, out)


def test_node_id_of_a_class_based_testcase():
    import xml.etree.ElementTree as ET
    tc = ET.fromstring('<testcase classname="tests.test_class.TestGreeter" name="test_inside" '
                       'file="tests/test_class.py" line="1"/>')
    assert sr.node_id(tc) == 'tests/test_class.py::TestGreeter::test_inside'
