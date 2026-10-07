# The TEST_AUTHOR Functions (plan 042, Phase 10): the requirement text the prompts show, the criterion prompt and its
# check, the test prompt, and the writer of one suite - whose output the real launcher then runs, so the suite format
# both sides use is pinned here, not only described. Every path is built under the test's own tmp_path.

import json
import os

import pytest

import nrvv_criterion_check as cc
import nrvv_criterion_prompt as cp
import nrvv_requirement_text as rt
import nrvv_suite_run as launcher
import nrvv_test_prompt as tp
import nrvv_test_write as tw

URL = 'https://github.com/sergmain/metaheuristic-assets.git'
SHA = '0123456789abcdef0123456789abcdef01234567'

# observed: TMPSN3F36BJ-3 at snapshot #62 (E1), exactly as mhdg_rg_query_req returned it
E1_REQUIREMENT = (
    "{{METADATA_ver=1}}\n##MH.INFO_BANK##Info Bank\nTMPSN3F36BJ\n##MH.INFO_BANK_DOCUMENT_NUMBER##Document number in Info "
    "Bank\n3\n##MH.DOCUMENT_TYPE##MH.DOCUMENT_TYPE\nRequirement\n##MH.DOCUMENT_NAME##MH.DOCUMENT_NAME\nRequirement\n"
    "##MH.DOCUMENT_DATE##Document date\n04.10.2026\n##MH.DOCUMENT_NUMBER##Document number\nTMPSN3F36BJ-3\n{{/METADATA}}\n"
    "{{M=1}}TMPSN 3F36BJ-3 Print 'Hello, NRVV' to output\n\n{{M=100}}1. Requirement content\n{{M=2}}1.1) When executed, "
    "the program must output the exact text 'Hello, NRVV' to standard output.\n\n{{M=101}}2. Rationale\n{{M=3}}2.1) The "
    "source document contains System.out.println('Hello, NRVV'), explicitly specifying this output requirement.\n\n"
    "{{M=4}}2.2) source: C:\\_mh\\mhbp_home-PostgreSQL-disk-storage\\nrvv\\_recovery\\1\\source\\nrvv\\synthetic\\source"
    "\\NrvvSample.java\n\n{{M=102}}3. Constraints\n{{M=5}}3.1) Not applicable.\n\n{{M=103}}4. Acceptance\n{{M=6}}4.1) Not "
    "applicable.\n")


def with_source(citation):
    return E1_REQUIREMENT.replace(
        'C:\\_mh\\mhbp_home-PostgreSQL-disk-storage\\nrvv\\_recovery\\1\\source\\nrvv\\synthetic\\source\\NrvvSample.java',
        citation)


# ---------------------------------------------------------------------------------------------------
# the requirement text

def test_plain_text_drops_the_metadata_block_and_the_markers_and_keeps_every_item():
    text = rt.plain_text(E1_REQUIREMENT)

    assert '{{' not in text and '##MH.' not in text
    assert text.startswith("TMPSN 3F36BJ-3 Print 'Hello, NRVV' to output")
    for item in ('1. Requirement content', "1.1) When executed, the program must output the exact text 'Hello, NRVV'",
                 '2. Rationale', '3. Constraints', '4. Acceptance', '4.1) Not applicable.'):
        assert item in text
    assert '\n\n\n' not in text


def test_plain_text_of_nothing_is_empty():
    assert rt.plain_text(None) == ''
    assert rt.plain_text('{{METADATA_ver=1}}\nx\n{{/METADATA}}\n') == ''


def test_the_source_citation_is_the_last_source_line():
    assert rt.source_citation(E1_REQUIREMENT).endswith('\\nrvv\\synthetic\\source\\NrvvSample.java')
    cited = URL + '@' + SHA + ':nrvv/synthetic/source-multi/Greeting.java'
    assert rt.source_citation(with_source(cited)) == cited
    assert rt.source_citation('1.1) no citation here') is None


@pytest.mark.parametrize('citation, module', [
    ('C:\\ws\\source\\nrvv\\synthetic\\source\\NrvvSample.java', 'nrvv_sample'),
    (URL + '@' + SHA + ':nrvv/synthetic/source-multi/Greeting.java', 'greeting'),
    (URL + '@' + SHA + ':src/HTTPServer.java', 'http_server'),
    (URL + '@' + SHA + ':Main.java', 'main'),
    (URL + '@' + SHA + ':a/3D.java', 'm_3_d'),
])
def test_the_module_is_the_snake_case_stem_of_the_source_file(citation, module):
    assert rt.module_name(with_source(citation)) == module


def test_a_requirement_without_a_source_file_targets_the_default_module():
    assert rt.module_name('{{M=2}}1.1) Must greet.') == rt.DEFAULT_MODULE


# ---------------------------------------------------------------------------------------------------
# the criterion prompt and its check

def test_the_criterion_prompt_words_source_language_constructs_as_behaviour():
    # C3 (TA2, TA4): requirements recovered from Java name Java constructs - 'public class', 'void main()',
    # System.out.println - and the criteria repeated them, which a Python implementation cannot meet literally
    prompt = cp.compose('TMPVOP59D8L-1', E1_REQUIREMENT)

    # the criterion must hold whatever language implements the requirement: a construct of the source language is
    # stated as the observable behaviour it implies
    assert 'ANY implementation language' in prompt
    assert 'never the construct itself' in prompt
    assert 'an access modifier' in prompt and 'a return type' in prompt and 'compiling' in prompt
    assert 'Name no test framework, no file and no programming language.' in prompt, 'the existing rule stays'


def test_the_criterion_prompt_carries_the_requirement_text_and_the_answer_shape():
    prompt = cp.compose(' TMPSN3F36BJ-3\n', E1_REQUIREMENT)

    assert 'Requirement TMPSN3F36BJ-3:' in prompt
    assert "1.1) When executed, the program must output the exact text 'Hello, NRVV'" in prompt
    assert '{"criterion": "<the criterion>"}' in prompt
    assert '{{M=' not in prompt and 'METADATA' not in prompt


@pytest.mark.parametrize('req_id, content', [('', E1_REQUIREMENT), ('X-1', ''), ('X-1', '{{M=1}}  \n')])
def test_the_criterion_prompt_refuses_an_empty_input(req_id, content):
    with pytest.raises(ValueError):
        cp.compose(req_id, content)


def test_the_criterion_check_collapses_whitespace_into_one_line():
    answer = json.dumps({'criterion': "Running main()  prints\n'Hello, NRVV'\tonce."})

    assert cc.criterion_of(answer) == "Running main() prints 'Hello, NRVV' once."


def test_the_criterion_check_unwraps_one_markdown_fence():
    assert cc.criterion_of('```json\n{"criterion": "It prints once."}\n```') == 'It prints once.'


@pytest.mark.parametrize('answer', ['not json', '["x"]', '{"criterion": "  "}', '{"text": "x"}', '', None,
                                    '{"criterion": 5}'])
def test_the_criterion_check_refuses_anything_but_one_criterion(answer):
    with pytest.raises(ValueError):
        cc.criterion_of(answer)


def test_the_criterion_check_counts_utf8_bytes_as_the_test_case_column_does():
    assert len(cc.criterion_of(json.dumps({'criterion': '\u0436' * 1000}))) == 1000
    with pytest.raises(ValueError, match='2002 UTF-8 bytes'):
        cc.criterion_of(json.dumps({'criterion': '\u0436' * 1001}))
    assert len(cc.criterion_of(json.dumps({'criterion': 'x' * 2000}))) == 2000
    with pytest.raises(ValueError, match='UTF-8 bytes'):
        cc.criterion_of(json.dumps({'criterion': 'x' * 2001}))


# ---------------------------------------------------------------------------------------------------
# the test prompt

def test_the_test_prompt_names_the_module_the_file_and_the_governed_criterion():
    prompt = tp.compose('TMPSN3F36BJ-3', E1_REQUIREMENT, " Running main() prints 'Hello, NRVV'.\n",
                        'TMPSN3F36BJ_7_suite', 'TMPSN3F36BJ-7')

    assert '`nrvv_sample`' in prompt
    assert 'tests/test_TMPSN3F36BJ_7_suite.py' in prompt
    assert "TEST_CASE TMPSN3F36BJ-7, criterion:\nRunning main() prints 'Hello, NRVV'." in prompt
    # CT Red (TA1, C1): the answer is the file alone - the writer derives the ids
    assert '{"testFile": "<the whole content of tests/test_TMPSN3F36BJ_7_suite.py>"}' in prompt
    assert 'testIds' not in prompt
    assert 'Requirement TMPSN3F36BJ-3:' in prompt
    assert '{{M=' not in prompt


@pytest.mark.parametrize('suite', ['', '7_suite', 'A__B_suite', 'A-1_suite', 'A_suite_'])
def test_the_test_prompt_refuses_what_is_not_a_suite_name(suite):
    with pytest.raises(ValueError, match='suite-name'):
        tp.compose('X-1', E1_REQUIREMENT, 'c', suite, 'X-2')


@pytest.mark.parametrize('field', ['req', 'criterion', 'tc'])
def test_the_test_prompt_refuses_an_empty_input(field):
    args = {'req': 'X-1', 'criterion': 'c', 'tc': 'X-2'}
    args[field] = ' '
    with pytest.raises(ValueError):
        tp.compose(args['req'], E1_REQUIREMENT, args['criterion'], 'X_2_suite', args['tc'])


# ---------------------------------------------------------------------------------------------------
# the writer

SUITE = 'TMPSN3F36BJ_7_suite'
PATH = 'tests/test_' + SUITE + '.py'
GOOD_TESTS = (
    'import nrvv_sample\n\n\n'
    'def test_main_prints_hello(capsys):\n'
    '    nrvv_sample.NrvvSample().main()\n'
    "    assert capsys.readouterr().out == 'Hello, NRVV\\n'\n\n\n"
    'def test_main_prints_one_line(capsys):\n'
    '    nrvv_sample.NrvvSample().main()\n'
    '    assert capsys.readouterr().out.count(\'\\n\') == 1\n')


def answer(source=GOOD_TESTS, ids=None):
    return json.dumps({'testFile': source,
                       'testIds': ids if ids is not None else [PATH + '::test_main_prints_hello',
                                                               PATH + '::test_main_prints_one_line']})


def test_parse_answer_returns_the_file_and_its_ids():
    source, ids = tw.parse_answer(answer(), SUITE)

    assert source == GOOD_TESTS
    assert ids == [PATH + '::test_main_prints_hello', PATH + '::test_main_prints_one_line']


def test_parse_answer_unwraps_one_markdown_fence():
    assert tw.parse_answer('```json\n' + answer() + '\n```', SUITE)[0] == GOOD_TESTS


# observed: TA1 (ExecContext #91), branch 2, Task 25250 - CC's test answer, Variable 13815, byte for byte. It carries
# the test file and no testIds, although the prompt asked for both.
TA1_BRANCH2_ANSWER = r"""{"testFile": "import inspect\n\nimport nrvv_sample\n\n\ndef _get_class():\n    cls = getattr(nrvv_sample, \"NrvvSample\", None)\n    assert cls is not None, \"module nrvv_sample must declare a class named 'NrvvSample'\"\n    assert inspect.isclass(cls), \"'NrvvSample' must be a class\"\n    return cls\n\n\ndef test_class_declares_main_member():\n    cls = _get_class()\n    assert \"main\" in dir(cls), \"class NrvvSample must declare a member named 'main'\"\n\n\ndef test_main_is_callable():\n    cls = _get_class()\n    main = getattr(cls, \"main\", None)\n    assert main is not None, \"class NrvvSample must have a 'main' method\"\n    assert callable(main), \"'main' must be callable (a method)\"\n\n\ndef test_main_is_a_function_or_method():\n    cls = _get_class()\n    main = inspect.getattr_static(cls, \"main\", None)\n    assert main is not None, \"class NrvvSample must declare 'main'\"\n    assert isinstance(\n        main, (staticmethod, classmethod)\n    ) or inspect.isfunction(main), \"'main' must be a method of NrvvSample\"\n"}"""


def test_the_ta1_answer_without_test_ids_is_refused():
    # CT Green-1 (TA1, correction C1 of the test-author flow): the answer is refused for its missing testIds
    # CT Red: it is accepted - the ids are the file's module-level test functions, in file order
    source, ids = tw.parse_answer(TA1_BRANCH2_ANSWER, SUITE)

    assert source.startswith('import inspect\n')
    assert ids == [PATH + '::test_class_declares_main_member', PATH + '::test_main_is_callable',
                   PATH + '::test_main_is_a_function_or_method']


@pytest.mark.parametrize('listed', [
    [],
    ['tests/test_other.py::test_main_prints_hello', PATH + '::test_main_prints_one_line'],
    [PATH + '::test_main_prints_hello'],
    [PATH + '::test_main_prints_hello', PATH + '::test_main_prints_one_line', PATH + '::test_x'],
    [PATH + '::test_main_prints_hello', PATH + '::test_main_prints_hello', PATH + '::test_main_prints_one_line'],
    'not a list',
])
def test_test_ids_in_the_answer_are_ignored_the_file_decides(listed):
    # CT Red (TA1, C1): these answers were refused for their testIds; the file alone now decides the suite
    source, ids = tw.parse_answer(json.dumps({'testFile': GOOD_TESTS, 'testIds': listed}), SUITE)

    assert source == GOOD_TESTS
    assert ids == [PATH + '::test_main_prints_hello', PATH + '::test_main_prints_one_line']


@pytest.mark.parametrize('bad, why', [
    ('not json', 'not JSON'),
    (json.dumps(['x']), 'no JSON object'),
    (json.dumps({'testIds': [PATH + '::test_main_prints_hello']}), 'no testFile'),
    (answer(source='def test_a(:\n    pass\n', ids=[PATH + '::test_a']), 'not valid Python'),
    (answer(source='class TestA:\n    def test_a(self):\n        pass\n', ids=[PATH + '::TestA']), 'test class'),
    (answer(source='def helper():\n    pass\n', ids=[PATH + '::helper']), 'defines no test function'),
    (json.dumps({'testFile': 'def helper():\n    pass\n'}), 'defines no test function'),
])
def test_parse_answer_refuses_before_anything_is_written(bad, why):
    with pytest.raises(ValueError, match=why):
        tw.parse_answer(bad, SUITE)


def test_write_suite_writes_exactly_the_test_file_and_the_suite_file(tmp_path):
    workspace = str(tmp_path / 'ws')
    base = os.path.join(workspace, 'test-suite', 'nrvv', 'synthetic', 'test-suite')
    os.makedirs(base)
    source, ids = tw.parse_answer(answer(), SUITE)

    report = tw.write_suite(workspace, {'url': URL, 'branchOrRef': 'b', 'dir': 'nrvv/synthetic/test-suite'}, SUITE,
                            source, ids)

    assert report == {'suite': SUITE, 'testFile': 'nrvv/synthetic/test-suite/' + PATH,
                      'suiteFile': 'nrvv/synthetic/test-suite/suites/' + SUITE + '.suite', 'testIds': ids}
    written = sorted(os.path.relpath(os.path.join(d, f), base).replace('\\', '/')
                     for d, _, fs in os.walk(base) for f in fs)
    assert written == ['suites/' + SUITE + '.suite', PATH]
    with open(os.path.join(base, 'suites', SUITE + '.suite'), encoding='utf-8', newline='') as f:
        assert f.read() == '# ' + SUITE + ' - written by nrvv-test-author\n' + '\n'.join(ids) + '\n'


def test_write_suite_overwrites_a_suite_a_rerun_rewrites(tmp_path):
    workspace = str(tmp_path / 'ws')
    location = {'url': URL, 'branchOrRef': 'b', 'dir': ''}
    os.makedirs(os.path.join(workspace, 'test-suite'))
    tw.write_suite(workspace, location, SUITE, 'def test_old():\n    pass\n', [PATH + '::test_old'])

    tw.write_suite(workspace, location, SUITE, GOOD_TESTS, [PATH + '::test_main_prints_hello'])

    with open(os.path.join(workspace, 'test-suite', 'suites', SUITE + '.suite'), encoding='utf-8') as f:
        assert 'test_old' not in f.read()


def test_write_suite_refuses_a_missing_checkout(tmp_path):
    with pytest.raises(ValueError, match='checked out'):
        tw.write_suite(str(tmp_path / 'ws'), {'url': URL, 'branchOrRef': 'b', 'dir': 'x'}, SUITE, GOOD_TESTS,
                       [PATH + '::test_main_prints_hello'])


def test_write_suite_into_a_fresh_dir_of_the_checkout(tmp_path):
    # plan 044, Phase 16: a fresh base directory, as the wizard names it - the checkout exists, its test-suite dir not yet
    workspace = str(tmp_path / 'ws')
    os.makedirs(os.path.join(workspace, 'test-suite'))
    location = {'url': URL, 'branchOrRef': 'b', 'dir': 'nrvv/synthetic/fresh/test-suite'}

    report = tw.write_suite(workspace, location, SUITE, GOOD_TESTS, [PATH + '::test_main_prints_hello'])

    base = os.path.join(workspace, 'test-suite', 'nrvv', 'synthetic', 'fresh', 'test-suite')
    assert report['suiteFile'] == 'nrvv/synthetic/fresh/test-suite/suites/' + SUITE + '.suite'
    assert os.path.isfile(os.path.join(base, 'suites', SUITE + '.suite'))
    assert os.path.isfile(os.path.join(base, *PATH.split('/')))


# ---------------------------------------------------------------------------------------------------
# the writer's suite, run by the real launcher (nrvv-suite-run, decision 14)

def written_suite(tmp_path, implementation):
    workspace = str(tmp_path / 'ws')
    base = os.path.join(workspace, 'test-suite', 'ts')
    target = os.path.join(workspace, 'target', 'tg')
    os.makedirs(base)
    os.makedirs(target)
    with open(os.path.join(target, 'nrvv_sample.py'), 'w', encoding='utf-8') as f:
        f.write(implementation)
    source, ids = tw.parse_answer(answer(), SUITE)
    tw.write_suite(workspace, {'url': URL, 'branchOrRef': 'b', 'dir': 'ts'}, SUITE, source, ids)
    return launcher.run_suite(base, SUITE, target, str(tmp_path / 'out'))


def test_the_launcher_runs_a_written_suite_and_passes_a_correct_target(tmp_path):
    entry = written_suite(tmp_path, "class NrvvSample:\n    def main(self):\n        print('Hello, NRVV')\n")

    assert entry['verdict'] == 'PASS', entry


def test_the_launcher_fails_a_written_suite_on_a_wrong_target(tmp_path):
    entry = written_suite(tmp_path, "class NrvvSample:\n    def main(self):\n        print('Hello')\n")

    assert entry['verdict'] == 'FAIL', entry


# ---------------------------------------------------------------------------------------------------
# the Functions, through their roles - the metas of nrvv-test-author-1.0

def task_with_inputs(working, metas, values, outputs):
    inputs = []
    for number, (name, text) in enumerate(values.items(), 1):
        os.makedirs(os.path.join(working, 'variable'), exist_ok=True)
        with open(os.path.join(working, 'variable', str(number)), 'w', encoding='utf-8') as f:
            f.write(text)
        inputs.append({'name': name, 'id': number, 'dataType': 'variable'})
    return {'workingPath': working, 'metas': metas, 'inputs': inputs,
            'outputs': [{'name': n, 'id': 100 + i} for i, n in enumerate(outputs, 1)]}


def artifact(working, output_id):
    with open(os.path.join(working, 'artifacts', str(output_id)), encoding='utf-8') as f:
        return f.read()


def test_run_criterion_prompt_and_check_through_their_roles(tmp_path):
    w1 = str(tmp_path / 'prompt')
    cp.run(task_with_inputs(w1, [{'variable-for-req-id': 'reqId'}, {'variable-for-requirement': 'requirementContent'},
                                 {'variable-for-prompt': 'criterionPrompt'}],
                            {'reqId': 'TMPSN3F36BJ-3\n', 'requirementContent': E1_REQUIREMENT}, ['criterionPrompt']))
    assert 'Requirement TMPSN3F36BJ-3:' in artifact(w1, 101)

    w2 = str(tmp_path / 'check')
    cc.run(task_with_inputs(w2, [{'variable-for-cc-result': 'criterionResult'}, {'variable-for-criterion': 'criterion'}],
                            {'criterionResult': '{"criterion": "It prints once."}'}, ['criterion']))
    assert artifact(w2, 101) == 'It prints once.'


def test_run_test_prompt_and_write_through_their_roles(tmp_path):
    w1 = str(tmp_path / 'prompt')
    tp.run(task_with_inputs(w1, [{'variable-for-req-id': 'reqId'}, {'variable-for-requirement': 'requirementContent'},
                                 {'variable-for-criterion': 'testCaseCriterion'}, {'variable-for-suite-name': 'suiteName'},
                                 {'variable-for-test-case-req-id': 'testCaseReqId'}, {'variable-for-prompt': 'testPrompt'}],
                            {'reqId': 'TMPSN3F36BJ-3', 'requirementContent': E1_REQUIREMENT,
                             'testCaseCriterion': 'It prints once.', 'suiteName': SUITE + '\n',
                             'testCaseReqId': 'TMPSN3F36BJ-7'}, ['testPrompt']))
    assert PATH in artifact(w1, 101)

    workspace = str(tmp_path / 'ws')
    os.makedirs(os.path.join(workspace, 'test-suite', 'ts'))
    w2 = str(tmp_path / 'write')
    tw.run(task_with_inputs(w2, [{'variable-for-workspace': 'workspace'}, {'variable-for-location': 'testSuite'},
                                 {'variable-for-suite-name': 'suiteName'}, {'variable-for-cc-result': 'testResult'},
                                 {'variable-for-suite-files': 'suiteFiles'}],
                            {'workspace': workspace + '\n', 'testSuite': json.dumps({'url': URL, 'branchOrRef': 'b', 'dir': 'ts'}),
                             'suiteName': SUITE, 'testResult': answer()}, ['suiteFiles']))
    report = json.loads(artifact(w2, 101))
    assert report['suiteFile'] == 'ts/suites/' + SUITE + '.suite'
    assert os.path.isfile(os.path.join(workspace, 'test-suite', 'ts', 'tests', 'test_' + SUITE + '.py'))
