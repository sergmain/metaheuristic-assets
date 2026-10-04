# Produces the launcher fixture that the Java side of NRVV parses (plan 042, Phase 12): REAL output of
# nrvv_suite_run over a small synthetic suite, never a hand-written look-alike.
#
#   python nrvv/tools/capture_launcher_fixture.py <work-dir> <fixture-dir>
#
# <work-dir>     scratch dir the synthetic test-suite / target / verification trees are built in (emptied first)
# <fixture-dir>  where report.json and the per-suite JUnit XML files are copied
#
# Suites: REQ_1_suite PASS, REQ_2_suite FAIL, REQ_3_suite ERROR (a listed id that does not exist),
# REQ_4_suite ERROR (pytest exit 5, nothing collected).
#
# Not shipped: only nrvv/payload/fn-nrvv reaches a Processor.

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'payload', 'fn-nrvv', 'src'))

import nrvv_suite_run as sr  # noqa: E402

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
    'tests/test_empty.py': '# no tests here\n',
    'suites/REQ_1_suite.suite': '# PASS\ntests/test_greeter.py::test_greets\ntests/test_greeter.py::test_greets_empty\n',
    'suites/REQ_2_suite.suite': '# FAIL\ntests/test_greeter.py::test_greets\ntests/test_broken.py::test_wrong\n',
    'suites/REQ_3_suite.suite': '# ERROR: a listed id that does not exist\ntests/test_greeter.py::test_nope\n',
    'suites/REQ_4_suite.suite': '# ERROR: pytest exit 5\ntests/test_empty.py\n',
}


def write(root, files):
    for rel, content in files.items():
        p = os.path.join(root, *rel.split('/'))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)


def main(work, fixture):
    shutil.rmtree(work, ignore_errors=True)
    ts, tg, out = (os.path.join(work, d) for d in ('test-suite', 'target', 'verification'))
    write(tg, TARGET)
    write(ts, TESTS)
    report = sr.run_suites(ts, tg, out)
    os.makedirs(fixture, exist_ok=True)
    with open(os.path.join(fixture, 'report.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
    for e in report:
        if e['xml']:
            shutil.copyfile(e['xml'], os.path.join(fixture, os.path.basename(e['xml'])))
    print(', '.join(e['suite'] + '=' + e['verdict'] for e in report))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
