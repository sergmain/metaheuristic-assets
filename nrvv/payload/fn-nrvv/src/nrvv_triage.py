# NRVV triage (plan 047, Phase 23, decision 17): after a VERIFICATION with FAIL or INCONCLUSIVE verdicts, ONE CC session
# classes every test that did not pass - why it did not:
#   CODE         the implementation is wrong; the test follows its criterion and the requirements in force
#   TEST         the test is wrong; it expects what its criterion does not ask, or what another requirement forbids
#   ENVIRONMENT  the simulated environment (tests/nrvv_env/) is wrong; it does not model the world the requirements state
#   REQUIREMENT  the requirement or its criterion is wrong; the test follows it, and it contradicts another requirement in
#                force or asks what no implementation can meet
# with a one-line reason each. The chain repairs by class (NrvvTriageService): REQUIREMENT -> REQ_CV and BACKTRACE on the
# baseline; TEST / ENVIRONMENT -> TEST_AUTHOR; CODE -> IMPLEMENTATION with the failure messages; then VERIFICATION.
#
# The context - input triageContext, written by the Dispatcher (NrvvTriageService) from the VERIFICATION's results:
#   {"tests": [{"test", "suite", "outcome", "message"}],
#    "suites": [{"suite", "testCaseReqId", "requirementReqId", "requirement", "criterion"}],
#    "requirements": "<every ACTIVE requirement of the snapshot, '<reqId>: <text>' blocks>"}
# A test id is a pytest node id relative to the test-suite dir; a suite that failed as a whole (nothing ran) is listed
# with its suite name as the test.
#
# The canonical answer: {"triage": [{"test", "suite", "triageClass", "reason"}]} - every test of the context exactly once,
# in the context's order. The Dispatcher's mhdg-nrvv.store-triage checks the same again against the VERIFICATION.
#
# Pure but for run_prompt() / run_check().

import json
import os

import mh_task_io as io
import nrvv_assessment as na
import nrvv_cc_answer as ca
import nrvv_paths

CLASSES = ('CODE', 'TEST', 'ENVIRONMENT', 'REQUIREMENT')
ITEM_FIELDS = ('test', 'suite', 'triageClass', 'reason')
MESSAGE_MAX_CHARS = 2000
REASON_MAX_CHARS = 400
ENV_DIR = ('tests', 'nrvv_env')
NO_FILE = '(the test-suite checkout has no such file)'

ANSWER_SHAPE = ('{"triage": [{"test": "<the test id as listed>", "suite": "<the suite as listed>", '
                '"triageClass": "<CODE|TEST|ENVIRONMENT|REQUIREMENT>", "reason": "<one line: the evidence>"}]}')
ANSWER_TAIL = 'Print nothing - neither the triage nor any explanation: only what the tool stores reaches the pipeline.'


def _text(value):
    return value if isinstance(value, str) else ''


def context_of(raw):
    """The triage context the Dispatcher wrote, or a ValueError naming the first violation."""
    try:
        data = json.loads(raw or '')
    except json.JSONDecodeError as e:
        raise ValueError('triageContext is not JSON: ' + str(e))
    if not isinstance(data, dict):
        raise ValueError('triageContext is not a JSON object')
    tests = data.get('tests')
    if not isinstance(tests, list) or not tests:
        raise ValueError('triageContext lists no test to triage')
    seen = set()
    for i, t in enumerate(tests):
        if not isinstance(t, dict):
            raise ValueError('test #' + str(i) + ' is not an object')
        for f in ('test', 'suite', 'outcome'):
            if not isinstance(t.get(f), str) or not t.get(f).strip():
                raise ValueError('test #' + str(i) + ' has no ' + f)
        key = (t['suite'], t['test'])
        if key in seen:
            raise ValueError('test #' + str(i) + ' (' + t['suite'] + ' ' + t['test'] + ') is listed twice')
        seen.add(key)
    suites = data.get('suites')
    if suites is None:
        suites = []
    if not isinstance(suites, list) or any(not isinstance(s, dict) for s in suites):
        raise ValueError('triageContext suites is not a list of objects')
    requirements = data.get('requirements')
    if requirements is not None and not isinstance(requirements, str):
        raise ValueError('triageContext requirements is not text')
    return {'tests': tests, 'suites': suites, 'requirements': requirements or ''}


def test_files(context):
    """The test files the listed tests name (the node id before '::', a .py file), in order of first appearance."""
    files = []
    for t in context['tests']:
        rel = t['test'].split('::', 1)[0].strip()
        if rel.endswith('.py') and rel not in files:
            files.append(rel)
    return files


def read_files(test_suite_dir, files):
    """{rel path: content}; a file the checkout does not have is given as NO_FILE - that is evidence, not a failure."""
    texts = {}
    for rel in files:
        path = os.path.join(test_suite_dir or '', *nrvv_paths.rel_parts(rel))
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                texts[rel] = f.read()
        else:
            texts[rel] = NO_FILE
    return texts


def read_env(test_suite_dir):
    """{file name: content} of <test-suite dir>/tests/nrvv_env/*.py; {} when there is no such package."""
    d = os.path.join(test_suite_dir or '', *ENV_DIR)
    if not os.path.isdir(d):
        return {}
    files = {}
    for name in sorted(f for f in os.listdir(d) if f.endswith('.py')):
        with open(os.path.join(d, name), encoding='utf-8') as f:
            files[name] = f.read()
    return files


def _message(text):
    m = _text(text).strip()
    return m if len(m) <= MESSAGE_MAX_CHARS else m[:MESSAGE_MAX_CHARS] + ' ... (cut)'


def compose(context, files, env_files):
    """The triage prompt; the answer instruction is its LAST part."""
    lines = [
        'You triage a failed verification. A Python implementation was verified against test suites, and the tests',
        'below did not pass: each FAILED, ERRORED, was SKIPPED (a precondition the test could not reach) or did not',
        'run. For each test decide WHY, and class it as exactly one of:',
        '',
        '- CODE: the implementation is wrong. The test follows its criterion and the requirements in force; the code',
        '  under test does not do what they ask.',
        '- TEST: the test is wrong. It expects something its criterion does not ask or another requirement in force',
        '  forbids, or it cannot reach its own precondition although the system behaves as required.',
        '- ENVIRONMENT: the simulated environment (tests/nrvv_env/) is wrong. It does not model the world the',
        '  requirements describe, or it gives the implementation no way to do what is required.',
        '- REQUIREMENT: the requirement or its criterion is wrong. The test follows it faithfully, but it contradicts',
        '  another requirement in force, or it asks for what no implementation can meet.',
        '',
        'Judge from the evidence below: the failure message, the test\'s code, its criterion and requirement, and the',
        'requirements in force. Class a test CODE only when the test itself is right. The reason is one line naming',
        'the evidence.',
        '',
        'Tests that did not pass - suite | test | outcome, then the message:',
    ]
    for t in context['tests']:
        lines.append('- ' + t['suite'] + ' | ' + t['test'] + ' | ' + t['outcome'])
        message = _message(t.get('message'))
        if message:
            lines.extend('    ' + m for m in message.splitlines())
    if context['suites']:
        lines += ['', 'The suites, with the requirement each verifies and its criterion:']
        for s in context['suites']:
            suite = _text(s.get('suite'))
            lines.append('=== ' + suite + ' verifies ' + _text(s.get('requirementReqId'))
                         + ' (criterion ' + _text(s.get('testCaseReqId')) + ') ===')
            lines.append('Requirement: ' + _text(s.get('requirement')).strip())
            lines.append('Criterion: ' + _text(s.get('criterion')).strip())
            lines.append('=== end of ' + suite + ' ===')
    if context['requirements'].strip():
        lines += ['', 'The requirements in force at this snapshot - read-only constraints:',
                  context['requirements'].strip()]
    if files:
        lines += ['', 'Test files:']
        for rel, content in files.items():
            lines.append('=== ' + rel + ' ===')
            lines.append(content.rstrip('\n'))
            lines.append('=== end of ' + rel + ' ===')
    if env_files:
        lines += ['', 'The simulated environment - tests/nrvv_env/:']
        for name, source in env_files.items():
            lines.append('=== tests/nrvv_env/' + name + ' ===')
            lines.append(source.rstrip('\n'))
            lines.append('=== end of tests/nrvv_env/' + name + ' ===')
    lines += [
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object and nothing else -',
        'one entry per test listed above, in the same order:',
        ANSWER_SHAPE,
        ANSWER_TAIL,
    ]
    return '\n'.join(lines)


def classes_of(cc_result, context):
    """CC's triage in canonical form, or a ValueError naming the first violation: every listed test exactly once, a
    known class, a one-line reason."""
    text = (cc_result or '').strip()
    fenced = na.FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    data = ca.loads(text)
    if not isinstance(data, dict):
        raise ValueError('CC answered no {"triage": [...]} object: ' + na.excerpt(text))
    extra = [k for k in data.keys() if k != 'triage']
    if extra:
        raise ValueError('the answer has an unknown field ' + repr(extra[0]))
    items = data.get('triage')
    if not isinstance(items, list):
        raise ValueError('triage is not a list')
    listed = [(t['suite'], t['test']) for t in context['tests']]
    by_key = {}
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError('triage #' + str(i) + ' is not an object')
        unknown = [k for k in item.keys() if k not in ITEM_FIELDS]
        if unknown:
            raise ValueError('triage #' + str(i) + ' has an unknown field ' + repr(unknown[0]))
        test = _text(item.get('test')).strip()
        suite = _text(item.get('suite')).strip()
        key = (suite, test)
        if key not in listed:
            raise ValueError('triage #' + str(i) + ' names ' + suite + ' ' + test + ', which is not a listed test')
        if key in by_key:
            raise ValueError('triage #' + str(i) + ' answers ' + suite + ' ' + test + ' a second time')
        cls = item.get('triageClass')
        if cls not in CLASSES:
            raise ValueError('triage #' + str(i) + ' has the unknown class ' + repr(cls))
        reason = _text(item.get('reason')).strip()
        if not reason:
            raise ValueError('triage #' + str(i) + ' (' + test + ') gives no reason')
        if '\n' in reason or '\r' in reason:
            raise ValueError('triage #' + str(i) + ' (' + test + ') gives a reason of more than one line')
        if len(reason) > REASON_MAX_CHARS:
            raise ValueError('triage #' + str(i) + ' (' + test + ') gives a reason of ' + str(len(reason))
                             + ' characters, at most ' + str(REASON_MAX_CHARS))
        by_key[key] = {'test': test, 'suite': suite, 'triageClass': cls, 'reason': reason}
    missing = [k for k in listed if k not in by_key]
    if missing:
        raise ValueError('the triage does not answer ' + missing[0][0] + ' ' + missing[0][1])
    return {'triage': [by_key[k] for k in listed]}


def run_prompt(task, function_code):
    context = context_of(io.read_role(task, 'triage-context'))
    test_suite_dir = (io.read_role(task, 'test-suite-dir') or '').strip()
    files = read_files(test_suite_dir, test_files(context))
    env_files = read_env(test_suite_dir)
    prompt = compose(context, files, env_files)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(function_code + ': ' + str(len(context['tests'])) + ' test(s), ' + str(len(files)) + ' test file(s), '
          + str(len(env_files)) + ' nrvv_env file(s), ' + str(len(prompt)) + ' chars')


def run_check(task, function_code):
    context = context_of(io.read_role(task, 'triage-context'))
    result = classes_of(io.read_role(task, 'cc-result'), context)
    io.write_text(io.output_role(task, 'triage'), json.dumps(result, ensure_ascii=False))
    counts = {}
    for item in result['triage']:
        counts[item['triageClass']] = counts.get(item['triageClass'], 0) + 1
    print(function_code + ': ' + ', '.join(c + ' ' + str(counts[c]) for c in CLASSES if c in counts))
