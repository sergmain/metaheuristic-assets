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
#
# THE ANSWER since plan 050 Phase 17 (2026-10-26, by its characterization test
# test_the_env_answer_is_the_files_under_their_header_lines): the files themselves, not {"files": {...}} - JSON inside the
# store tool's one string is two escaping levels, the slip that cost acceptance run (b) #119 six test answers on the API
# path (no closing '"}') and left #107's environment answer one '}' too many on the CC path. Every file is opened by a line
# under its own `--- tests/nrvv_env/<name>.py` and followed by its Python source - the form the test prompt shows nrvv_env in.

import ast
import json
import os
import re
import shutil
import sys

import nrvv_requirement_text as rt

PACKAGE = 'nrvv_env'
ENV_DIR = 'tests/' + PACKAGE
# plan 050 Phase 17: the line that opens a file of the answer
HEADER = '--- ' + ENV_DIR + '/'
HEADER_LINE = re.compile(r'^--- ' + re.escape(ENV_DIR) + r'/(.*)$')
FILE_NAME = re.compile(r'[a-z][a-z0-9_]*\.py')
INIT = '__init__.py'
FORBIDDEN = ('threading', '_thread', 'multiprocessing', 'asyncio', 'concurrent', 'time', 'socket', 'subprocess')
FENCE = re.compile(r'^```[A-Za-z]*\s*\n(.*)\n```$', re.DOTALL)
EXCERPT = 300
# what may follow the decoded answer object: whitespace and stray closers only (plan 045 Phase 36: haiku stored a whole
# files object and one '}' more) - anything else after the object is content, and is refused
STRAY_CLOSERS = re.compile(r'[\s}\]]*')


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
        # plan 047 Phase 21: an event index orders what happens at one instant; the ports are closed to tests
        '- Every recorded send, delivery and acknowledgement carries a global `event_index`: ONE counter for the whole',
        '  simulation, increasing by one per event - a test orders events that happen at one instant by it.',
        '- Hand `app` its ports inside `connect` as closures (functions defined inside `connect`), never as public',
        '  methods or functions of the package: a test must not be able to call a port itself, only drive `app`.',
        '- Deterministic: no thread, no clock, no real I/O. Any randomness only through a random.Random(seed) instance',
        '  built from the seed the test gives; the same seed gives the same run.',
        '- The standard library and `' + PACKAGE + '` itself only; never threading, _thread, multiprocessing, asyncio,',
        '  concurrent, time, socket or subprocess.',
        '- File names: lowercase Python module names ending in .py; none starting with test_ or ending with _test.py -',
        '  the package lives next to the tests and must not be collected as one. __init__.py is optional.',
        '- No tests: the tests are written separately, against your package.',
        '',
        # plan 047 Phase 20 (by its characterization test): the answer instruction moved to the END, as every v5
        # prompt's. It was here:
        #   'Store your answer with the result tool as exactly this JSON object, and nothing else:',
        #   '{"files": {"__init__.py": "<content>", "<module>.py": "<content>"}}',
        #   '',
        'The Interface - the boundary of the server side:',
        '',
        items_text(design['interface']),
        '',
        'The Environment - what you simulate:',
        '',
        items_text(design['environment']),
        '',
        # plan 050 Phase 17 (by its characterization test test_the_env_prompt_asks_for_the_files_under_their_header_lines):
        # the files themselves under header lines. It was:
        #   'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object, and nothing else:',
        #   '{"files": {"__init__.py": "<content>", "<module>.py": "<content>"}}',
        'Answer by calling the mh_cc_store_result tool exactly once, with the files of the package as the result: each file'
        ' opened by a line "' + HEADER + '<name>.py" and followed by its Python source - nothing before the first such'
        ' line, no JSON, no markdown fence:',
        HEADER + INIT,
        '<content>',
        HEADER + '<module>.py',
        '<content>',
        'Print nothing - neither the files nor any explanation: only what the tool stores reaches the pipeline.',
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


# plan 047 Phase 21: a name the Interface gives is an identifier written right before '(' - "set_price(station, price)"; no
# space allowed, so prose such as "result (a price)" names nothing
INTERFACE_NAME = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\(')


def snake_case(name):
    """A name bound to Python: setPrice -> set_price; set_price stays."""
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name).lower()


def interface_names(design):
    """Plan 047 Phase 21: every operation and port name the Interface items give, bound to Python (snake_case)."""
    names = set()
    for item in design.get('interface') or []:
        for name in INTERFACE_NAME.findall(rt.plain_text(item.get('content'))):
            names.add(snake_case(name))
    return names


def check_ports(files, design):
    """Plan 047 Phase 21: a ValueError when a file of nrvv_env exposes a PUBLIC function or method - defined at module level
    or in a class body, no leading '_' - named as an Interface operation or port. The ports are handed to `app` as
    closures inside `connect`, so a test cannot call one on the simulation instead of driving `app`."""
    names = interface_names(design)
    if not names:
        return
    for name, source in sorted(files.items()):
        tree = ast.parse(source, filename=name)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith('_') and node.name in names:
                raise ValueError(name + ': ' + node.name + " is public and named as the Interface's " + node.name
                                 + ' - hand app its ports as closures inside connect')
            if isinstance(node, ast.ClassDef):
                for member in node.body:
                    if (isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and not member.name.startswith('_')
                            and member.name in names):
                        raise ValueError(name + ': ' + node.name + '.' + member.name + " is public and named as the"
                                         + " Interface's " + member.name + ' - hand app its ports as closures inside connect')


def split_files(text):
    """{file name: content} of the files carried under their header lines (plan 050 Phase 17), in answer order. A ValueError
    for text before the first header line, for no header line at all, or for a file given twice. A file's content is its
    lines up to the next header line, trailing blank lines dropped and one newline kept; a file with no text is empty."""
    files = {}
    current = None
    body = []
    for line in text.replace('\r\n', '\n').split('\n'):
        header = HEADER_LINE.match(line)
        if header:
            if current is not None:
                files[current] = _file_text(body)
            current = header.group(1).strip()
            if current in files:
                raise ValueError("file '" + current + "' is given twice")
            body = []
        elif current is not None:
            body.append(line)
        elif line.strip():
            raise ValueError('CC answered text before the first "' + HEADER + '<name>.py" line: ' + excerpt(text))
    if current is None:
        raise ValueError('CC answered no file under a "' + HEADER + '<name>.py" line: ' + excerpt(text))
    files[current] = _file_text(body)
    return files


def _file_text(lines):
    text = '\n'.join(lines).rstrip('\n')
    return text + '\n' if text.strip() else ''


def parse_env_answer(cc_result):
    """{file name: content} of CC's answer, checked before anything is written - or a ValueError naming the rule."""
    text = (cc_result or '').strip()
    fenced = FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    # plan 050 Phase 17: the files under their header lines (split_files); it was the shared JSON decode of every NRVV
    # check, nrvv_cc_answer.loads, over {"files": {...}}
    files = split_files(text)
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
