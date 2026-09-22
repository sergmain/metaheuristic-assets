# mh_rg_req_store_batch: the run's (model, effort) pair that store sends to RG (requirements/manual/first and
# mhdg_rg_open_stage), so the snapshots it seals record the pair that actually wrote the requirements.
from mh_rg_req_store_batch import llm_pair, optional_role


def task_with(tmp_path, metas, inputs, files=None):
    (tmp_path / 'variable').mkdir(exist_ok=True)
    for var_id, text in (files or {}).items():
        (tmp_path / 'variable' / str(var_id)).write_text(text, encoding='utf-8')
    return {'workingPath': str(tmp_path), 'metas': metas, 'inputs': inputs}


def test_optional_role_reads_the_bound_variable_stripped(tmp_path):
    task = task_with(tmp_path, [{'variable-for-model': 'model'}], [{'id': 7, 'name': 'model'}], {7: ' claude-sonnet-4-6\n'})

    assert optional_role(task, 'model') == 'claude-sonnet-4-6'


def test_optional_role_is_none_when_the_process_binds_no_variable(tmp_path):
    # mh-rg-requirements-from-batch-1.4 binds model/effort only to cc, not to store
    assert optional_role(task_with(tmp_path, [], []), 'model') is None


def test_optional_role_is_none_for_a_nullified_variable(tmp_path):
    task = task_with(tmp_path, [{'variable-for-effort': 'effort'}], [{'id': 8, 'name': 'effort', 'empty': True}])

    assert optional_role(task, 'effort') is None


def test_optional_role_is_none_for_blank_text(tmp_path):
    task = task_with(tmp_path, [{'variable-for-effort': 'effort'}], [{'id': 8, 'name': 'effort'}], {8: '  \n'})

    assert optional_role(task, 'effort') is None


def test_llm_pair_carries_only_what_was_given():
    assert llm_pair('claude-sonnet-4-6', 'medium') == {'model': 'claude-sonnet-4-6', 'effort': 'medium'}
    assert llm_pair('claude-sonnet-4-6', None) == {'model': 'claude-sonnet-4-6'}
    assert llm_pair(None, 'medium') == {'effort': 'medium'}
    assert llm_pair(None, None) == {}


def test_an_unbound_pair_leaves_the_requests_unchanged():
    # what run() builds for mhdg_rg_open_stage when nothing is bound - exactly the pre-1.5 arguments
    assert dict({'infoBank': 'TMP1', 'parentSnapshotId': 5}, **llm_pair(None, None)) == {'infoBank': 'TMP1', 'parentSnapshotId': 5}
