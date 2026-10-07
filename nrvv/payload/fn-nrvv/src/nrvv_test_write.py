# mh.asset.nrvv-test-write_1.0 - check CC's test answer and write ONE suite into the test-suite checkout: the test
# file tests/test_<suite>.py and the suite file suites/<suite>.suite (plan 042, decisions 13 and 14; Phase 10).
#
# Inputs  (process metas variable-for-<role>):
#   workspace    absolute path of the run workspace
#   location     the NRVV project's test-suite location, JSON {"url", "branchOrRef", "dir"}
#   suite-name   NrvvNamingUtils.suiteName of the TEST_CASE's lineage root
#   cc-result    CC's answer, stored through call-cc's result tool:
#                {"testFile": "<content of tests/test_<suite>.py>", "testIds": ["tests/test_<suite>.py::<name>", ...]}
# Output:
#   suite-files  JSON {"suite", "testFile", "suiteFile", "testIds"} - the two files, repository-relative
#
# CC WRITES NO FILE: it answers content, and this Function writes exactly the two files of the suite, under `tests/`
# and `suites/` of the test-suite dir - the plan's "writes only under tests/ and suites/" holds by construction.
# Both are overwritten when they exist: a re-run rewrites an affected TEST_CASE's tests and suite (plan, Phase 10).
#
# THE CHECKS, all before anything is written: the answer is one JSON object; the test file parses as Python (ast -
# parsed, never executed); every listed id is `tests/test_<suite>.py::<name>` naming a module-level `test_*` function
# of that file, and the ids name EVERY such function exactly once - a suite must not leave a test of its own file
# unrun; no module-level class whose name pytest would collect (Test*): its tests could not be listed.
#
# Since TA1 (2026-10-04, correction C1 of the test-author flow, nrvv/DETAILS.md): the suite's ids are DERIVED from the
# test file - its module-level test_* functions, in file order - and any testIds in the answer are ignored. CC left
# them out in one branch of four (ExecContext #91, Task 25250) while the file alone decides which tests exist, so
# asking for them added nothing but a way to fail. The checks on the file itself stay.
#
# Pure but for write_suite()/run()/main(): no git, no network, no subprocess.

import ast
import json
import os
import re
import sys

import mh_task_io as io
import nrvv_paths
from nrvv_checkout import parse_location

FUNCTION_CODE = 'mh.asset.nrvv-test-write_1.0'

SUITE_NAME = re.compile(r'[a-zA-Z][a-zA-Z0-9]*(?:_[a-zA-Z0-9]+)*')
FENCE = re.compile(r'^```[A-Za-z]*\s*\n(.*)\n```$', re.DOTALL)
EXCERPT = 300


def excerpt(text):
    text = text or ''
    return text if len(text) <= EXCERPT else text[:EXCERPT] + '...'


def the_suite_name(text):
    suite = (text or '').strip()
    if not SUITE_NAME.fullmatch(suite):
        raise ValueError("suite-name is not a suite name: '" + suite + "'")
    return suite


def test_file(suite):
    return 'tests/test_' + suite + '.py'


def suite_file(suite):
    return 'suites/' + suite + '.suite'


def module_level_tests(source, path):
    """The names of the module-level test_* functions of a test file, in file order; a ValueError when the file does
    not parse or defines a module-level class pytest would collect."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as e:
        raise ValueError(path + ' is not valid Python: line ' + str(e.lineno) + ': ' + str(e.msg)) from None
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test'):
            names.append(node.name)
        elif isinstance(node, ast.ClassDef) and node.name.startswith('Test'):
            raise ValueError(path + ' defines the test class ' + node.name + ': tests are module-level functions')
    return names


def parse_answer(cc_result, suite):
    """(test file content, test ids) of CC's answer for suite - or a ValueError listing every problem at once."""
    text = (cc_result or '').strip()
    fenced = FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError('CC answered something that is not JSON: ' + excerpt(text)) from None
    if not isinstance(data, dict):
        raise ValueError('CC answered no JSON object {"testFile": ..., "testIds": [...]}: ' + excerpt(text))
    source = data.get('testFile')
    if not isinstance(source, str) or not source.strip():
        raise ValueError('CC answered no testFile: ' + excerpt(text))

    path = test_file(suite)
    defined = module_level_tests(source, path)
    if not defined:
        raise ValueError('CC answer refused before anything was written: ' + path + ' defines no test function')
    # the suite runs every module-level test of its file, in file order (testIds of the answer are ignored, see above)
    return source, [path + '::' + name for name in defined]


def suite_text(suite, ids):
    """The suite file: a comment line, then one test id per line (decision 14)."""
    return '# ' + suite + ' - written by nrvv-test-author\n' + '\n'.join(ids) + '\n'


def write_suite(workspace, location, suite, source, ids):
    """Writes both files under the test-suite dir; returns the suite-files report."""
    # plan 044, Phase 16: a fresh base directory is not in the repository yet - the checkout must exist, the dir is
    # created inside it (as nrvv_implement does for the target)
    root = nrvv_paths.checkout_root(workspace, 'test-suite')
    if not os.path.isdir(root):
        raise ValueError('the test-suite checkout does not exist - was it checked out? ' + root)
    base = nrvv_paths.dir_path(workspace, 'test-suite', location['dir'])
    os.makedirs(base, exist_ok=True)
    files = {test_file(suite): source if source.endswith('\n') else source + '\n',
             suite_file(suite): suite_text(suite, ids)}
    for rel, content in files.items():
        target = os.path.join(base, *rel.split('/'))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
    rel_dir = nrvv_paths.rel_posix(location['dir'])
    in_repo = (lambda rel: rel_dir + '/' + rel) if rel_dir else (lambda rel: rel)
    return {'suite': suite, 'testFile': in_repo(test_file(suite)), 'suiteFile': in_repo(suite_file(suite)),
            'testIds': ids}


def run(task):
    workspace = nrvv_paths.require_workspace((io.read_role(task, 'workspace') or '').strip())
    location = parse_location(io.read_role(task, 'location'))
    suite = the_suite_name(io.read_role(task, 'suite-name'))
    source, ids = parse_answer(io.read_role(task, 'cc-result'), suite)
    report = write_suite(workspace, location, suite, source, ids)
    io.write_text(io.output_role(task, 'suite-files'), json.dumps(report, ensure_ascii=True))
    print(FUNCTION_CODE + ': ' + report['suiteFile'] + ', ' + str(len(ids)) + ' test(s)')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
