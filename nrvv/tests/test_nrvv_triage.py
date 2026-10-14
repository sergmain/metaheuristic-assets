# NRVV triage (plan 047, Phase 23, decision 17): the TRIAGE prompt - what it lists and its tail - every refusal of the
# check, and the repair section of the implement prompt the triage's CODE failures feed.

import json
import os

import pytest

import nrvv_implement as im
import nrvv_triage as tr

CONTEXT = {
    'tests': [
        {'test': 'tests/test_a.py::test_latest_price_settles', 'suite': 'GAS_12_suite', 'outcome': 'FAIL',
         'message': 'AssertionError: station S1 holds 101, expected 102'},
        {'test': 'tests/test_b.py::test_reordered_ack', 'suite': 'GAS_13_suite', 'outcome': 'SKIPPED',
         'message': 'precondition not reached: two sends in flight'},
        {'test': 'GAS_14_suite', 'suite': 'GAS_14_suite', 'outcome': 'ERROR', 'message': 'suite verdict ERROR, exit 4'},
    ],
    'suites': [
        {'suite': 'GAS_12_suite', 'testCaseReqId': 'GAS-22', 'requirementReqId': 'GAS-12',
         'requirement': 'Each station settles on the latest price.', 'criterion': 'After the last send, S holds it.'},
    ],
    'requirements': 'GAS-12: Each station settles on the latest price.\n\nGAS-13: Sends may arrive out of order.',
}


def answer(*items):
    return json.dumps({'triage': [dict(zip(tr.ITEM_FIELDS, i)) for i in items]})


VALID = [
    ('tests/test_a.py::test_latest_price_settles', 'GAS_12_suite', 'CODE', 'the code keeps the first price it sent'),
    ('tests/test_b.py::test_reordered_ack', 'GAS_13_suite', 'TEST', 'the test waits for an ack nrvv_env never reorders'),
    ('GAS_14_suite', 'GAS_14_suite', 'ENVIRONMENT', 'nrvv_env fails to import: the port is missing'),
]


def test_the_prompt_lists_every_test_and_ends_with_the_answer_instruction():
    prompt = tr.compose(tr.context_of(json.dumps(CONTEXT)), {'tests/test_a.py': 'def test_latest_price_settles(): pass\n'},
                        {'world.py': 'class World: pass\n'})
    lines = prompt.split('\n')
    assert lines[-1] == tr.ANSWER_TAIL, 'the answer instruction is the LAST part'
    assert lines[-2] == tr.ANSWER_SHAPE
    assert 'mh_cc_store_result' in lines[-4]
    for t in CONTEXT['tests']:
        assert '- ' + t['suite'] + ' | ' + t['test'] + ' | ' + t['outcome'] in lines
        assert '    ' + t['message'] in lines
    for cls in tr.CLASSES:
        assert '- ' + cls + ':' in prompt
    assert '=== GAS_12_suite verifies GAS-12 (criterion GAS-22) ===' in lines
    assert 'GAS-13: Sends may arrive out of order.' in prompt
    assert '=== tests/test_a.py ===' in lines and '=== tests/nrvv_env/world.py ===' in lines
    assert prompt.index('Tests that did not pass') < prompt.index('Test files:') < prompt.index('Answer by calling')


def test_the_prompt_leaves_out_empty_sections_and_cuts_a_long_message():
    context = tr.context_of(json.dumps({'tests': [{'test': 't.py::x', 'suite': 'S', 'outcome': 'FAIL',
                                                   'message': 'x' * (tr.MESSAGE_MAX_CHARS + 50)}]}))
    prompt = tr.compose(context, {}, {})
    assert 'The suites, with' not in prompt and 'read-only constraints' not in prompt
    assert 'Test files:' not in prompt and '=== tests/nrvv_env/' not in prompt
    assert '    ' + 'x' * tr.MESSAGE_MAX_CHARS + ' ... (cut)' in prompt.split('\n')


def test_classes_of_gives_the_canonical_triage_in_the_context_order():
    result = tr.classes_of('```json\n' + answer(*reversed(VALID)) + '\n```', tr.context_of(json.dumps(CONTEXT)))
    assert result == {'triage': [dict(zip(tr.ITEM_FIELDS, i)) for i in VALID]}


@pytest.mark.parametrize('raw, message', [
    ('not json', 'not JSON'),
    ('[]', 'no {"triage"'),
    (json.dumps({'triage': [], 'note': 'x'}), "unknown field 'note'"),
    (json.dumps({'triage': {}}), 'triage is not a list'),
    (answer(*VALID, ('tests/test_c.py::x', 'GAS_12_suite', 'CODE', 'r')), 'which is not a listed test'),
    (answer(*VALID, VALID[0]), 'a second time'),
    (answer(*VALID[:2]), 'does not answer GAS_14_suite GAS_14_suite'),
    (answer(VALID[0], VALID[1], ('GAS_14_suite', 'GAS_14_suite', 'NETWORK', 'r')), "unknown class 'NETWORK'"),
    (answer(VALID[0], VALID[1], ('GAS_14_suite', 'GAS_14_suite', 'TEST', ' ')), 'gives no reason'),
    (answer(VALID[0], VALID[1], ('GAS_14_suite', 'GAS_14_suite', 'TEST', 'a\nb')), 'more than one line'),
    (answer(VALID[0], VALID[1], ('GAS_14_suite', 'GAS_14_suite', 'TEST', 'r' * (tr.REASON_MAX_CHARS + 1))), 'at most'),
    (json.dumps({'triage': [dict(zip(tr.ITEM_FIELDS, VALID[0]), message='m')]}), "unknown field 'message'"),
])
def test_classes_of_refuses(raw, message):
    with pytest.raises(ValueError) as e:
        tr.classes_of(raw, tr.context_of(json.dumps(CONTEXT)))
    assert message in str(e.value)


@pytest.mark.parametrize('raw, message', [
    ('not json', 'not JSON'),
    ('[]', 'not a JSON object'),
    (json.dumps({'tests': []}), 'no test to triage'),
    (json.dumps({'tests': [{'test': 'a', 'suite': 'S'}]}), 'has no outcome'),
    (json.dumps({'tests': [{'test': 'a', 'suite': 'S', 'outcome': 'FAIL'}] * 2}), 'listed twice'),
    (json.dumps({'tests': [{'test': 'a', 'suite': 'S', 'outcome': 'FAIL'}], 'suites': {}}), 'suites is not a list'),
    (json.dumps({'tests': [{'test': 'a', 'suite': 'S', 'outcome': 'FAIL'}], 'requirements': 1}), 'requirements is not text'),
])
def test_context_of_refuses(raw, message):
    with pytest.raises(ValueError) as e:
        tr.context_of(raw)
    assert message in str(e.value)


def test_test_files_and_a_missing_file_is_evidence(tmp_path):
    context = tr.context_of(json.dumps(CONTEXT))
    assert tr.test_files(context) == ['tests/test_a.py', 'tests/test_b.py'], 'a suite that failed as a whole names no file'
    os.makedirs(tmp_path / 'tests')
    (tmp_path / 'tests' / 'test_a.py').write_text('def test_latest_price_settles(): pass\n', encoding='utf-8')
    files = tr.read_files(str(tmp_path), tr.test_files(context))
    assert files['tests/test_a.py'].startswith('def test_latest_price_settles')
    assert files['tests/test_b.py'] == tr.NO_FILE


def test_read_env(tmp_path):
    assert tr.read_env(str(tmp_path)) == {}, 'no tests/nrvv_env package - no section'
    os.makedirs(tmp_path / 'tests' / 'nrvv_env')
    (tmp_path / 'tests' / 'nrvv_env' / 'world.py').write_text('W = 1\n', encoding='utf-8')
    (tmp_path / 'tests' / 'nrvv_env' / 'notes.txt').write_text('x', encoding='utf-8')
    assert tr.read_env(str(tmp_path)) == {'world.py': 'W = 1\n'}


def _task(tmp_path, metas, inputs, outputs):
    work = tmp_path / 'work'
    for i, (name, text) in enumerate(inputs.items()):
        p = work / 'variable' / str(i + 1)
        os.makedirs(p.parent, exist_ok=True)
        p.write_text(text, encoding='utf-8')
    return {'workingPath': str(work), 'metas': [{k: v} for k, v in metas.items()],
            'inputs': [{'name': n, 'id': i + 1, 'dataType': 'variable'} for i, n in enumerate(inputs)],
            'outputs': [{'name': n, 'id': 100 + i} for i, n in enumerate(outputs)]}


def test_run_prompt_and_run_check(tmp_path):
    suite_dir = tmp_path / 'ts'
    os.makedirs(suite_dir / 'tests')
    (suite_dir / 'tests' / 'test_a.py').write_text('def test_latest_price_settles(): pass\n', encoding='utf-8')
    task = _task(tmp_path, {'variable-for-triage-context': 'triageContext', 'variable-for-test-suite-dir': 'dir',
                            'variable-for-prompt': 'prompt'},
                 {'triageContext': json.dumps(CONTEXT), 'dir': str(suite_dir) + '\n'}, ['prompt'])
    tr.run_prompt(task, 'mh.asset.nrvv-triage-prompt_1.0')
    prompt = (tmp_path / 'work' / 'artifacts' / '100').read_text(encoding='utf-8')
    assert '=== tests/test_a.py ===' in prompt and tr.NO_FILE in prompt

    task = _task(tmp_path / 'c', {'variable-for-cc-result': 'cc', 'variable-for-triage-context': 'triageContext',
                                  'variable-for-triage': 'triage'},
                 {'cc': answer(*VALID), 'triageContext': json.dumps(CONTEXT)}, ['triage'])
    tr.run_check(task, 'mh.asset.nrvv-triage-check_1.0')
    stored = json.loads((tmp_path / 'c' / 'work' / 'artifacts' / '100').read_text(encoding='utf-8'))
    assert [i['triageClass'] for i in stored['triage']] == ['CODE', 'TEST', 'ENVIRONMENT']


# ---------------------------------------------------------------- the implement prompt of a repair round

IMPL_SUITES = [('GAS_12_suite', ['tests/test_a.py::test_latest_price_settles'])]
IMPL_TEXTS = {'tests/test_a.py': 'def test_latest_price_settles(): pass\n'}


def test_the_implement_prompt_without_failures_is_unchanged():
    plain = im.compose_prompt('C:/ws/target/tg', 'C:/ws/test-suite/ts', IMPL_SUITES, IMPL_TEXTS, ['GAS_13_suite'])
    assert im.compose_prompt('C:/ws/target/tg', 'C:/ws/test-suite/ts', IMPL_SUITES, IMPL_TEXTS, ['GAS_13_suite'],
                             None, None, None) == plain
    assert im.compose_prompt('C:/ws/target/tg', 'C:/ws/test-suite/ts', IMPL_SUITES, IMPL_TEXTS, ['GAS_13_suite'],
                             None, None, '  \n') == plain
    assert 'This is a repair' not in plain


def test_the_implement_prompt_of_a_repair_carries_the_failures_before_the_suites():
    failures = 'GAS_12_suite | tests/test_a.py::test_latest_price_settles\n    AssertionError: holds 101, expected 102'
    prompt = im.compose_prompt('C:/ws/target/tg', 'C:/ws/test-suite/ts', IMPL_SUITES, IMPL_TEXTS, [], None, None,
                               failures + '\n')
    assert failures in prompt
    assert prompt.index('This is a repair') < prompt.index(failures) < prompt.index('Suites - every line')
