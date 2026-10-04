# mh.asset.nrvv-test-prompt_1.0 - the CC prompt that writes the pytest file verifying ONE TEST_CASE (plan 042,
# Phase 10).
#
# Inputs  (process metas variable-for-<role>):
#   req-id             the requirement's current reqId - the splitter's line
#   requirement        the requirement as mhdg-rg.read-req read it at the run's STAGE (RG document markup)
#   criterion          the TEST_CASE's criterion AS GOVERNED IN RG - mhdg-nrvv.store-test-case's testCaseCriterion: the
#                      new criterion on create, the existing TEST_CASE's text when the lineage already had one
#   suite-name         NrvvNamingUtils.suiteName of the TEST_CASE's lineage root (decision 13)
#   test-case-req-id   the TEST_CASE the suite verifies
# Output:
#   prompt             the prompt for mh.asset.call-cc_1.1
#
# INDEPENDENCE (decision 17): the prompt carries the requirement and the criterion, never target code; CC gets no
# checkout at all. It answers with the file's CONTENT and its test ids as one JSON object, and
# mh.asset.nrvv-test-write_1.0 writes tests/test_<suite>.py and suites/<suite>.suite - CC writes no file anywhere.
#
# THE MODULE: tests import the module nrvv_requirement_text.module_name names - the snake_case stem of the file the
# requirement was recovered from - so every suite of one source file targets one module.
#
# Pure but for run()/main().

import re
import sys

import mh_task_io as io
import nrvv_requirement_text as rt

FUNCTION_CODE = 'mh.asset.nrvv-test-prompt_1.0'

SUITE_NAME = re.compile(r'[a-zA-Z][a-zA-Z0-9]*(?:_[a-zA-Z0-9]+)*')
MAX_TESTS = 10


def test_file(suite_name):
    """The test file of a suite, relative to the test-suite dir: tests/test_<suite>.py."""
    return 'tests/test_' + suite_name + '.py'


def the_suite_name(text):
    suite = (text or '').strip()
    if not SUITE_NAME.fullmatch(suite):
        raise ValueError("suite-name is not a suite name: '" + suite + "'")
    return suite


def compose(req_id, content, criterion, suite_name, test_case_req_id):
    """The prompt, or a ValueError naming the input that cannot make one."""
    req = (req_id or '').strip()
    tc = (test_case_req_id or '').strip()
    crit = ' '.join((criterion or '').split())
    if not req:
        raise ValueError('req-id is empty')
    if not tc:
        raise ValueError('test-case-req-id is empty')
    if not crit:
        raise ValueError('criterion is empty')
    suite = the_suite_name(suite_name)
    text = rt.plain_text(content)
    if not text:
        raise ValueError('requirement ' + req + ' has no text')
    module = rt.module_name(content)
    path = test_file(suite)
    return '\n'.join([
        'You write the automated tests that verify ONE requirement of a software system that is being ported to Python.',
        '',
        'You have the requirement and its verification criterion, and nothing else. There is no implementation for you',
        'to read, and you must not ask for one: these tests define what the implementation has to provide.',
        '',
        'The implementation under test:',
        '- is the Python module `' + module + '`, importable as `import ' + module + '` (it is on PYTHONPATH);',
        '- ports the source file the requirement was recovered from: it keeps that file\'s class names and spells',
        '  method and function names in snake_case (a method `main` stays `main`; an instance method is called on an',
        '  instance created with no arguments unless the requirement says otherwise);',
        '- text printed to standard output is checked with pytest\'s `capsys` fixture.',
        '',
        'Write ONE pytest file, ' + path + ':',
        '- every test checks the criterion below; at least 1 test and at most ' + str(MAX_TESTS) + ';',
        '- tests are module-level functions named test_<what it checks>; no classes;',
        '- the standard library and pytest only; no network; files only under pytest\'s tmp_path.',
        '',
        'Store your answer with the result tool as exactly this JSON object, and nothing else:',
        '{"testFile": "<the whole content of ' + path + '>", "testIds": ["' + path + '::<test function>", ...]}',
        'testIds names every test function of the file, as a pytest node id relative to the test-suite root.',
        '',
        'TEST_CASE ' + tc + ', criterion:',
        crit,
        '',
        'Requirement ' + req + ':',
        text,
    ])


def run(task):
    prompt = compose(io.read_role(task, 'req-id'), io.read_role(task, 'requirement'), io.read_role(task, 'criterion'),
                     io.read_role(task, 'suite-name'), io.read_role(task, 'test-case-req-id'))
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(FUNCTION_CODE + ': ' + str(len(prompt)) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
