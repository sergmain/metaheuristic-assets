# The simulated environment of a definition (plan 043, Phase 9): the CC prompt for the Python package `nrvv_env`, and
# the checks and the write of CC's answer. Pure but for write_env(). The Function scripts are nrvv_env_prompt and
# nrvv_env_write; this module is not named nrvv_env so that it can never shadow the package it writes.
#
# The server side is the module `app` the implementation run writes; everything outside it - the clients and the
# transport - is the Environment of the definition, and the TEST side simulates it (decision 3): `nrvv_env`, written
# into <test-suite dir>/tests/nrvv_env/ before the per-requirement tests, never by the implementer - the party whose code
# must pass does not choose the world it is tested in.
#
# DETERMINISTIC BY CONSTRUCTION: every file is parsed (ast, never executed) and may import the standard library and
# nrvv_env only, never threading, _thread, multiprocessing, asyncio, concurrent, time, socket or subprocess - no
# thread, no clock, no real I/O. Randomness only through seeded random.Random instances is a rule of the prompt.
#
# PLACEMENT: tests/ carries no __init__.py, so pytest's default (prepend) import mode puts tests/ on sys.path for every
# test under it - `import nrvv_env` resolves there both under the launcher (nrvv_suite_run, cwd = the test-suite dir) and
# under the implementer's `python -m pytest <test-suite dir>` (cwd = the target dir). No file of the package may be one
# pytest collects (test_*.py, *_test.py).

import ast
import json
import os
import re
import shutil
import sys

import nrvv_requirement_text as rt

PACKAGE = 'nrvv_env'
ENV_DIR = 'tests/' + PACKAGE
FILE_NAME = re.compile(r'[a-z][a-z0-9_]*\.py')
INIT = '__init__.py'
FORBIDDEN = ('threading', '_thread', 'multiprocessing', 'asyncio', 'concurrent', 'time', 'socket', 'subprocess')
FENCE = re.compile(r'^```[A-Za-z]*\s*\n(.*)\n```$', re.DOTALL)
EXCERPT = 300


def excerpt(text):
    text = text or ''
    return text if len(text) <= EXCERPT else text[:EXCERPT] + '...'


def parse_design(design_json):
    """The design list-scope wrote: {"interface": [{"reqId", "content"}], "environment": [...]}. A ValueError when it is
    not that, or holds no Interface or no Environment item - there is nothing to simulate around."""
    try:
        design = json.loads(design_json or '')
    except ValueError:
        raise ValueError('design is not JSON: ' + excerpt(design_json)) from None
    if not isinstance(design, dict):
        raise ValueError('design is not a JSON object: ' + excerpt(design_json))
    for part in ('interface', 'environment'):
        items = design.get(part)
        if not isinstance(items, list) or not items:
            raise ValueError("design has no '" + part + "' item: " + excerpt(design_json))
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('reqId'), str) or not rt.plain_text(item.get('content')):
                raise ValueError("an item of design '" + part + "' has no reqId or no text: " + excerpt(json.dumps(item)))
    return design


def items_text(items):
    return '\n\n'.join(i['reqId'] + ':\n' + rt.plain_text(i['content']) for i in items)


def compose_env_prompt(design):
    """The prompt asking CC for the package nrvv_env that simulates the Environment around the Interface."""
    return '\n'.join([
        'You write the SIMULATED ENVIRONMENT of a system under test: the Python package `' + PACKAGE + '`.',
        '',
        'The system under test is the SERVER SIDE, implemented elsewhere as the Python module `app`. Its Interface is',
        'below, stated language-neutrally; in Python its operations are snake_case functions or methods of `app` and its',
        'types are CapWords classes of `app`. Everything outside the server side - its clients, and the transport between',
        'them and the server side - is the Environment below. It is not implemented: your package simulates it, exactly',
        'as described, so that tests can drive `app` through it and observe the clients.',
        '',
        'Rules:',
        '- Simulate exactly the Environment: the clients\' behaviour and the transport\'s ordering, delivery and',
        '  acknowledgement rules. Do not implement the server side; add no behaviour the Environment does not state.',
        '- `' + PACKAGE + '` never imports `app`: a test imports `app` and hands it, or what it provides, to `' + PACKAGE + '`,',
        '  which connects it to the simulated clients through the ports the Interface names.',
        '- Give a test what it needs: to build the simulation from a seed, to drive `app` through the transport step by',
        '  step until nothing is in flight, and to observe every client and the traffic (what was sent, delivered and',
        '  acknowledged).',
        '- Deterministic: no thread, no clock, no real I/O. Any randomness only through a random.Random(seed) instance',
        '  built from the seed the test gives; the same seed gives the same run.',
        '- The standard library and `' + PACKAGE + '` itself only; never threading, _thread, multiprocessing, asyncio,',
        '  concurrent, time, socket or subprocess.',
        '- File names: lowercase Python module names ending in .py; none starting with test_ or ending with _test.py -',
        '  the package lives next to the tests and must not be collected as one. __init__.py is optional.',
        '- No tests: the tests are written separately, against your package.',
        '',
        'Store your answer with the result tool as exactly this JSON object, and nothing else:',
        '{"files": {"__init__.py": "<content>", "<module>.py": "<content>"}}',
        '',
        'The Interface - the boundary of the server side:',
        '',
        items_text(design['interface']),
        '',
        'The Environment - what you simulate:',
        '',
        items_text(design['environment']),
    ])


def check_imports(name, source):
    """A ValueError naming the first import of `source` that is not the standard library or nrvv_env, or a forbidden
    one; a file that does not parse is refused too."""
    try:
        tree = ast.parse(source, filename=name)
    except SyntaxError as e:
        raise ValueError(name + ' is not valid Python: line ' + str(e.lineno) + ': ' + str(e.msg)) from None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                continue  # relative: inside nrvv_env
            modules = [node.module or '']
        else:
            continue
        for module in modules:
            top = module.split('.')[0]
            if top in FORBIDDEN:
                raise ValueError(name + ' imports ' + module + ': ' + ', '.join(FORBIDDEN) + ' are forbidden - no thread,'
                                 + ' no clock, no real I/O')
            if top != PACKAGE and top not in sys.stdlib_module_names:
                raise ValueError(name + ' imports ' + module + ', which is neither the standard library nor ' + PACKAGE)


def parse_env_answer(cc_result):
    """{file name: content} of CC's answer, checked before anything is written - or a ValueError naming the rule."""
    text = (cc_result or '').strip()
    fenced = FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError('CC answered something that is not JSON: ' + excerpt(text)) from None
    files = data.get('files') if isinstance(data, dict) else None
    if not isinstance(files, dict) or not files:
        raise ValueError('CC answered no JSON object {"files": {"<module>.py": "<content>"}}: ' + excerpt(text))
    for name, content in sorted(files.items()):
        if not isinstance(name, str) or not (name == INIT or FILE_NAME.fullmatch(name)):
            raise ValueError("file name '" + str(name) + "' is not a lowercase module name ending in .py")
        if name.startswith('test_') or name.endswith('_test.py'):
            raise ValueError("file name '" + name + "' would be collected by pytest as a test file")
        if not isinstance(content, str):
            raise ValueError(name + ' has no text content')
        check_imports(name, content)
    return dict(sorted(files.items()))


def write_env(test_suite_dir, rel_dir, files):
    """Replace <test-suite dir>/tests/nrvv_env/ with `files`, adding an empty __init__.py when missing; return the
    repository-relative paths written, sorted."""
    env_dir = os.path.join(test_suite_dir, *ENV_DIR.split('/'))
    if os.path.isdir(env_dir):
        shutil.rmtree(env_dir)
    os.makedirs(env_dir)
    written = dict(files)
    written.setdefault(INIT, '')
    for name, content in written.items():
        with open(os.path.join(env_dir, name), 'w', encoding='utf-8', newline='\n') as f:
            f.write(content if content == '' or content.endswith('\n') else content + '\n')
    prefix = rel_dir + '/' if rel_dir else ''
    return sorted(prefix + ENV_DIR + '/' + name for name in written)
