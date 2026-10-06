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
# Since TA1 (2026-10-04, correction C1, nrvv/DETAILS.md): CC answers the file alone, {"testFile": ...}; the writer
# derives the suite's ids from it. Asking for testIds as well made one answer in four fail for omitting them.
#
# DESIGN MODE (plan 043, Phase 10) - two OPTIONAL roles, read only when the process declares them:
#   design    the design mhdg-nrvv.list-scope wrote, {"interface": [{"reqId", "content"}], "environment": [...]}
#   env-dir   the test-suite dir: the prompt reads <env-dir>/tests/nrvv_env/ from the checkout, where
#             mh.asset.nrvv-env-write_1.0 wrote it (never an output of a `when`-gated process: a skipped gate would
#             leave such an input uninitialised and stall the run)
# With a design that has Interface items, the implementation under test is the module `app` - the Interface's names
# bound to Python (snake_case functions and methods, CapWords classes) - driven only through the package nrvv_env,
# whose files the prompt gives in full; every test is deterministic. Without one (the role undeclared, the Variable
# NULLIFIED, or a design with no Interface item) the prompt is byte-identical to the v1 prompt.
#
# Pure but for run()/main().

import json
import os
import re
import sys

import mh_task_io as io
import nrvv_requirement_text as rt

FUNCTION_CODE = 'mh.asset.nrvv-test-prompt_1.0'

SUITE_NAME = re.compile(r'[a-zA-Z][a-zA-Z0-9]*(?:_[a-zA-Z0-9]+)*')
MAX_TESTS = 10
ENV_DIR = ('tests', 'nrvv_env')


def test_file(suite_name):
    """The test file of a suite, relative to the test-suite dir: tests/test_<suite>.py."""
    return 'tests/test_' + suite_name + '.py'


def the_suite_name(text):
    suite = (text or '').strip()
    if not SUITE_NAME.fullmatch(suite):
        raise ValueError("suite-name is not a suite name: '" + suite + "'")
    return suite


def interface_items(design_json):
    """The Interface items of a design ([{"reqId", "content"}]), or [] for no design / a design without Interface."""
    if design_json is None or not design_json.strip():
        return []
    try:
        design = json.loads(design_json)
    except ValueError:
        raise ValueError('design is not JSON: ' + design_json[:300]) from None
    items = design.get('interface') if isinstance(design, dict) else None
    if not isinstance(items, list):
        raise ValueError('design has no "interface" list: ' + design_json[:300])
    return items


def read_env_files(env_dir):
    """{file name: content} of <env-dir>/tests/nrvv_env/*.py, by name - or a ValueError when there is no package."""
    d = os.path.join(env_dir or '', *ENV_DIR)
    names = sorted(f for f in os.listdir(d) if f.endswith('.py')) if os.path.isdir(d) else []
    if not names:
        raise ValueError('a design is given but there is no tests/nrvv_env package under ' + str(env_dir)
                         + ' - the environment Tasks write it before the tests are written')
    files = {}
    for name in names:
        with open(os.path.join(d, name), 'r', encoding='utf-8') as f:
            files[name] = f.read()
    return files


def compose(req_id, content, criterion, suite_name, test_case_req_id, interface=None, env_files=None):
    """The prompt, or a ValueError naming the input that cannot make one. `interface` and `env_files` given: the
    design-mode prompt; not given: the v1 prompt, unchanged."""
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
    if interface:
        return compose_design_mode(req, text, crit, suite, tc, interface, env_files)
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
        '{"testFile": "<the whole content of ' + path + '>"}',
        'Every module-level test_ function of the file becomes part of the suite.',
        '',
        'TEST_CASE ' + tc + ', criterion:',
        crit,
        '',
        'Requirement ' + req + ':',
        text,
    ])


def compose_design_mode(req, text, crit, suite, tc, interface, env_files):
    """The prompt for a requirement of a definition snapshot: the module `app`, its Interface, and nrvv_env in full."""
    if not env_files:
        raise ValueError('a design is given but no nrvv_env file')
    path = test_file(suite)
    lines = [
        'You write the automated tests that verify ONE requirement of a software system written in Python.',
        '',
        'You have the requirement, its verification criterion, the Interface of the system and the simulation of its',
        'environment, and nothing else. There is no implementation for you to read, and you must not ask for one: these',
        'tests define what the implementation has to provide.',
        '',
        'The implementation under test:',
        '- is the Python module `app`, importable as `import app` (it is on PYTHONPATH);',
        '- provides the Interface below, bound to Python: every operation is a snake_case function or method of `app`,',
        '  every type a CapWords class of `app`;',
        '- talks to everything outside it only through the simulated environment: the package `nrvv_env`, importable as',
        '  `import nrvv_env` - its files are given in full below. Use them as they are; never change or copy them.',
        '',
        'Write ONE pytest file, ' + path + ':',
        '- every test checks the criterion below; at least 1 test and at most ' + str(MAX_TESTS) + ';',
        '- tests are module-level functions named test_<what it checks>; no classes;',
        '- every test drives `app` only through `nrvv_env` - no other fake, stub or mock of anything;',
        '- every test is deterministic: fixed seeds only (several seeds per property are allowed), no clock, no threads;',
        '- the standard library, pytest, `app` and `nrvv_env` only; no network; files only under pytest\'s tmp_path.',
        '',
        'Store your answer with the result tool as exactly this JSON object, and nothing else:',
        '{"testFile": "<the whole content of ' + path + '>"}',
        'Every module-level test_ function of the file becomes part of the suite.',
        '',
        'TEST_CASE ' + tc + ', criterion:',
        crit,
        '',
        'Requirement ' + req + ':',
        text,
        '',
        'The Interface of `app`:',
    ]
    for item in interface:
        lines += ['', str(item.get('reqId')) + ':', rt.plain_text(item.get('content'))]
    lines += ['', 'The package `nrvv_env` (tests/nrvv_env/):']
    for name, source in env_files.items():
        lines += ['', '--- tests/nrvv_env/' + name, source.rstrip('\n')]
    return '\n'.join(lines)


def run(task):
    metas = task.get('metas') or []
    interface = interface_items(io.read_role(task, 'design')) if io.meta_value(metas, 'variable-for-design') else []
    env_files = read_env_files((io.read_role(task, 'env-dir') or '').strip()) if interface else None
    prompt = compose(io.read_role(task, 'req-id'), io.read_role(task, 'requirement'), io.read_role(task, 'criterion'),
                     io.read_role(task, 'suite-name'), io.read_role(task, 'test-case-req-id'), interface, env_files)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(FUNCTION_CODE + ': ' + str(len(prompt)) + ' chars')


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
