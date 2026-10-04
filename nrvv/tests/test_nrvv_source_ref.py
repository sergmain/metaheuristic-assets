# The citation of a recovered file - repository + revision + repository-relative path - and its substitution into the
# branch's checked answer (correction C1, nrvv/DETAILS.md). Every path is built under the test's own tmp_path, so every
# expected citation is written down before the code runs.

import json
import os

import pytest

import nrvv_source_ref as sr

URL = 'https://github.com/sergmain/metaheuristic-assets.git'
SHA = '0123456789abcdef0123456789abcdef01234567'


def location(dir_):
    return {'url': URL, 'branchOrRef': 'master', 'dir': dir_}


def answer_line(path, requirements=None):
    # exactly how mh.asset.rg-req-check_1.0 writes it: sourcePath first, one line of ASCII JSON
    return json.dumps({'sourcePath': path,
                       'requirements': requirements or [{'name': 'N', 'content': 'C \u00fc', 'rationale': 'R'}]},
                      ensure_ascii=True)


# ---------------------------------------------------------------------------------------------------
# the citation

def test_source_ref_names_url_commit_dir_and_the_file_relative_to_dir_path(tmp_path):
    dir_path = os.path.join(str(tmp_path), 'source', 'nrvv', 'synthetic', 'source')
    file = os.path.join(dir_path, 'NrvvSample.java')

    assert sr.source_ref(location('nrvv/synthetic/source'), SHA, dir_path, file) == \
        URL + '@' + SHA + ':nrvv/synthetic/source/NrvvSample.java'


def test_a_nested_file_is_cited_in_forward_slashes(tmp_path):
    dir_path = os.path.join(str(tmp_path), 'source', 'src')
    file = os.path.join(dir_path, 'main', 'java', 'A.java')

    assert sr.source_ref(location('src'), SHA, dir_path, file) == URL + '@' + SHA + ':src/main/java/A.java'


def test_the_repository_root_as_dir_cites_the_file_alone(tmp_path):
    dir_path = os.path.join(str(tmp_path), 'source')
    file = os.path.join(dir_path, 'a', 'B.java')

    assert sr.source_ref(location(''), SHA, dir_path, file) == URL + '@' + SHA + ':a/B.java'


def test_dir_is_cited_in_gits_spelling(tmp_path):
    dir_path = os.path.join(str(tmp_path), 'source', 'a', 'b')
    file = os.path.join(dir_path, 'C.java')

    assert sr.source_ref(location('./a\\b/'), SHA, dir_path, file) == URL + '@' + SHA + ':a/b/C.java'


def test_a_file_outside_dir_path_is_refused(tmp_path):
    dir_path = os.path.join(str(tmp_path), 'source', 'src')
    sibling = os.path.join(str(tmp_path), 'source', 'other', 'A.java')

    with pytest.raises(ValueError, match='not a file under dir-path'):
        sr.source_ref(location('src'), SHA, dir_path, sibling)


def test_dir_path_itself_is_refused(tmp_path):
    dir_path = os.path.join(str(tmp_path), 'source', 'src')

    with pytest.raises(ValueError, match='not a file under dir-path'):
        sr.source_ref(location('src'), SHA, dir_path, dir_path)


# ---------------------------------------------------------------------------------------------------
# the inputs

@pytest.mark.parametrize('text, expected', [
    (SHA, SHA),
    (' ' + SHA + '\n', SHA),
    ('a' * 64, 'a' * 64),
])
def test_the_commit_is_a_full_sha(text, expected):
    assert sr.the_commit(text) == expected


@pytest.mark.parametrize('text', [None, '', '0123abc', SHA.upper(), SHA + '\n' + SHA, 'master'])
def test_the_commit_refuses_anything_but_one_full_sha(text):
    with pytest.raises(ValueError, match='commit'):
        sr.the_commit(text)


def test_one_line_strips_and_refuses_none_or_several():
    assert sr.one_line('  x \n\n', 'source-path') == 'x'
    with pytest.raises(ValueError, match='source-path'):
        sr.one_line('', 'source-path')
    with pytest.raises(ValueError, match='source-path'):
        sr.one_line('a\nb', 'source-path')


def test_a_relative_path_is_refused():
    with pytest.raises(ValueError, match='not an absolute path'):
        sr.absolute('relative/A.java', 'source-path')


# ---------------------------------------------------------------------------------------------------
# the answer

def test_ref_answer_replaces_the_source_path_and_nothing_else(tmp_path):
    file = os.path.join(str(tmp_path), 'source', 'A.java')
    ref = URL + '@' + SHA + ':A.java'
    original = answer_line(file)

    rewritten = sr.ref_answer(original, file, ref)

    expected = json.loads(original)
    expected['sourcePath'] = ref
    assert json.loads(rewritten) == expected
    assert list(json.loads(rewritten)) == ['sourcePath', 'requirements']
    assert '\n' not in rewritten
    assert rewritten.isascii()


def test_ref_answer_refuses_an_answer_about_another_file(tmp_path):
    file = os.path.join(str(tmp_path), 'source', 'A.java')
    other = os.path.join(str(tmp_path), 'source', 'B.java')

    with pytest.raises(ValueError, match='not the branch'):
        sr.ref_answer(answer_line(other), file, URL + '@' + SHA + ':A.java')


@pytest.mark.parametrize('text', ['not json', '[1]', '{"sourcePath": "x"}', '{"requirements": []}', ''])
def test_ref_answer_refuses_anything_but_one_checked_answer(tmp_path, text):
    with pytest.raises(ValueError, match='answer'):
        sr.ref_answer(text, os.path.join(str(tmp_path), 'A.java'), 'ref')


# ---------------------------------------------------------------------------------------------------
# the Function, through its roles - the metas are those of the `ref` process of nrvv-recovery-sourceref-1.0

REF_METAS = [{'variable-for-location': 'source'}, {'variable-for-commit': 'sourceCommit'},
             {'variable-for-dir-path': 'sourceDirPath'}, {'variable-for-source-path': 'sourcePath'},
             {'variable-for-answer': 'reqAnswer'}, {'variable-for-source-ref': 'sourceRef'},
             {'variable-for-ref-answer': 'reqAnswerRef'}]


def task_with_inputs(working, values):
    inputs = []
    for number, (name, text) in enumerate(values.items(), 1):
        os.makedirs(os.path.join(working, 'variable'), exist_ok=True)
        with open(os.path.join(working, 'variable', str(number)), 'w', encoding='utf-8') as f:
            f.write(text)
        inputs.append({'name': name, 'id': number, 'dataType': 'variable'})
    return {'workingPath': working, 'metas': REF_METAS, 'inputs': inputs,
            'outputs': [{'name': 'sourceRef', 'id': 101}, {'name': 'reqAnswerRef', 'id': 102}]}


def test_run_writes_one_citation_to_both_outputs_so_the_store_pairs_them(tmp_path):
    working = str(tmp_path / 'task')
    dir_path = os.path.join(str(tmp_path), 'ws', 'source', 'nrvv', 'synthetic', 'source-multi')
    file = os.path.join(dir_path, 'Counter.java')
    task = task_with_inputs(working, {
        'source': json.dumps(location('nrvv/synthetic/source-multi')),
        'sourceCommit': SHA + '\n',
        'sourceDirPath': dir_path,
        'sourcePath': file + '\n',
        'reqAnswer': answer_line(file),
    })

    sr.run(task)

    with open(os.path.join(working, 'artifacts', '101'), encoding='utf-8') as f:
        ref = f.read()
    with open(os.path.join(working, 'artifacts', '102'), encoding='utf-8') as f:
        rewritten = json.loads(f.read())
    assert ref == URL + '@' + SHA + ':nrvv/synthetic/source-multi/Counter.java'
    # rg-req-store-stage pairs the answer with its `paths` line by string equality
    assert rewritten['sourcePath'] == ref
