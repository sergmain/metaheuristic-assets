# mh.asset.nrvv-suite-run_1.0 - the Python launcher of plan 042, decision 14.
#
# A suite is data: <test-suite dir>/suites/<SUITE_NAME>.suite, one pytest node id per line, '#' comments allowed.
# The launcher runs exactly the listed ids:
#     python -m pytest <ids...> --junitxml=<workspace>/verification/<SUITE_NAME>.xml
# with the test-suite dir as cwd and rootdir, and the target dir on PYTHONPATH, and reads the XML back.
#
# Verdict per suite:
#   ERROR  any listed id did not run (not collected, not found, skipped), pytest exit not in {0, 1} - exit 5,
#          "nothing collected", above all - any listed id erroring, or a suite listing nothing at all
#   FAIL   everything listed ran, some failed
#   PASS   everything listed ran and passed, exit 0
# A runner that silently runs nothing must not pass, so "did it run" is decided from the XML, per listed id.
#
# A listed id covers the results it names: itself, its parametrizations (id[...]) and, for a file or a class,
# everything under it (id::...).
#
# Inputs:  workspace, test-suite-location, target-location (JSON {url, branchOrRef, dir}),
#          suites (JSON array of suite names; NULLIFIED = every suite file)
# Output:  report - JSON array of {suite, listedIds, exitCode, missingIds, verdict, xml, tests, message}

import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import mh_task_io as io
import nrvv_checkout
import nrvv_paths

SUITE_NAME = re.compile(r'^[a-zA-Z][a-zA-Z0-9]*(_[a-zA-Z0-9]+)*$')
SUITES_DIR = 'suites'
SUITE_EXT = '.suite'


def read_suite(path):
    """The listed ids of one suite file: stripped, blank lines and '#' lines dropped, order kept."""
    ids = []
    for line in io.read_text(path).splitlines():
        s = line.strip()
        if s and not s.startswith('#'):
            ids.append(s.replace('\\', '/'))
    return ids


def suite_names(test_suite_dir):
    """Every suite under <test-suite dir>/suites, sorted."""
    d = os.path.join(test_suite_dir, SUITES_DIR)
    if not os.path.isdir(d):
        return []
    return sorted(f[:-len(SUITE_EXT)] for f in os.listdir(d) if f.endswith(SUITE_EXT))


def node_id(testcase):
    """The pytest node id of one <testcase> written with junit_family=xunit1 (which carries `file`)."""
    file = (testcase.get('file') or '').replace('\\', '/')
    classname = testcase.get('classname') or ''
    module = file[:-3].replace('/', '.') if file.endswith('.py') else file.replace('/', '.')
    cls = classname[len(module) + 1:] if classname.startswith(module + '.') else ''
    return file + ('::' + cls.replace('.', '::') if cls else '') + '::' + (testcase.get('name') or '')


def read_results(xml_path):
    """node id -> (outcome, message) from a JUnit XML file; outcome in PASS | FAIL | ERROR | NOT_RUN."""
    results = {}
    for tc in ET.parse(xml_path).getroot().iter('testcase'):
        outcome, message = 'PASS', None
        for child in tc:
            if child.tag == 'failure':
                outcome, message = 'FAIL', child.get('message')
            elif child.tag == 'error':
                outcome, message = 'ERROR', child.get('message')
            elif child.tag == 'skipped':
                outcome, message = 'NOT_RUN', child.get('message')
        results[node_id(tc)] = (outcome, message)
    return results


def outcome_of(listed_id, results):
    """(outcome, message) of one listed id over the results it covers; NOT_RUN when it covers nothing that ran."""
    covered = [v for k, v in results.items()
               if k == listed_id or k.startswith(listed_id + '[') or k.startswith(listed_id + '::')]
    ran = [v for v in covered if v[0] != 'NOT_RUN']
    if not ran:
        return 'NOT_RUN', (covered[0][1] if covered else 'did not run')
    for wanted in ('ERROR', 'FAIL'):
        hit = [v for v in ran if v[0] == wanted]
        if hit:
            return wanted, hit[0][1]
    return 'PASS', None


def verdict_of(exit_code, tests, missing):
    if missing or exit_code not in (0, 1) or any(t['outcome'] == 'ERROR' for t in tests):
        return 'ERROR'
    if any(t['outcome'] == 'FAIL' for t in tests):
        return 'FAIL'
    return 'PASS' if exit_code == 0 else 'ERROR'


def run_suite(test_suite_dir, suite_name, target_dir, out_dir, python=None):
    """Run one suite; return its report entry."""
    if not SUITE_NAME.match(suite_name):
        raise ValueError("invalid suite name '" + suite_name + "'")
    listed = read_suite(os.path.join(test_suite_dir, SUITES_DIR, suite_name + SUITE_EXT))
    entry = {'suite': suite_name, 'listedIds': listed, 'exitCode': None, 'missingIds': [], 'verdict': 'ERROR',
             'xml': None, 'tests': [], 'message': None}
    if not listed:
        # never run pytest with no ids: that collects EVERYTHING, and would pass a suite that lists nothing
        entry['message'] = 'suite lists no test id'
        return entry

    os.makedirs(out_dir, exist_ok=True)
    xml = os.path.join(out_dir, suite_name + '.xml')
    if os.path.exists(xml):
        os.remove(xml)    # a stale XML from a previous attempt must not stand in for this one
    env = dict(os.environ)
    env['PYTHONPATH'] = target_dir + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    cmd = [python or sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-o', 'junit_family=xunit1',
           '--rootdir', test_suite_dir, '--junitxml', xml] + listed
    r = subprocess.run(cmd, cwd=test_suite_dir, env=env, capture_output=True, text=True, encoding='utf-8',
                       check=False)
    entry['exitCode'] = r.returncode
    results = read_results(xml) if os.path.exists(xml) else {}
    entry['xml'] = xml if os.path.exists(xml) else None
    tests = []
    for listed_id in listed:
        outcome, message = outcome_of(listed_id, results)
        tests.append({'testId': listed_id, 'outcome': outcome, 'message': message})
    entry['tests'] = tests
    entry['missingIds'] = [t['testId'] for t in tests if t['outcome'] == 'NOT_RUN']
    entry['verdict'] = verdict_of(r.returncode, tests, entry['missingIds'])
    if entry['verdict'] == 'ERROR' and r.returncode not in (0, 1):
        entry['message'] = 'pytest exit ' + str(r.returncode) + ': ' + (r.stdout + r.stderr).strip()[-2000:]
    return entry


def run_suites(test_suite_dir, target_dir, out_dir, names=None, python=None):
    return [run_suite(test_suite_dir, n, target_dir, out_dir, python) for n in (names or suite_names(test_suite_dir))]


def main(argv):
    task = io.load_params(argv)['task']
    workspace = io.read_role(task, 'workspace').strip()
    ts = nrvv_checkout.parse_location(io.read_role(task, 'test-suite-location'))
    tg = nrvv_checkout.parse_location(io.read_role(task, 'target-location'))
    names_text = io.read_role(task, 'suites')
    names = json.loads(names_text) if names_text and names_text.strip() else None
    report = run_suites(nrvv_paths.dir_path(workspace, 'test-suite', ts['dir']),
                        nrvv_paths.dir_path(workspace, 'target', tg['dir']),
                        nrvv_paths.verification_dir(workspace), names)
    io.write_text(io.output_role(task, 'report'), json.dumps(report))
    print('nrvv-suite-run: ' + ', '.join(e['suite'] + '=' + e['verdict'] for e in report))


if __name__ == '__main__':
    main(sys.argv)
