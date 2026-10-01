# Opening the STAGE of an empty project: what is sent to RG's MCP tool mhdg_rg_open_stage, and what is accepted from
# its answer. The answer keeps the shape the tool declares (MhdgMcpToolDefinitions.pleOpenStageTool: "Returns
# {stageSnapshotId, parentSnapshotId}", RgPleAuthoringService.OpenStageResult); the values are synthetic.

import pytest

import mh_rg_open_stage as fn


def test_the_arguments_name_the_project_and_never_a_parent():
    arguments = fn.open_stage_arguments('TMPSYNTH01', 'claude-opus-4-8', 'medium')

    assert arguments == {'infoBank': 'TMPSYNTH01', 'model': 'claude-opus-4-8', 'effort': 'medium'}
    assert 'parentSnapshotId' not in arguments


def test_a_model_that_takes_no_effort_sends_the_model_alone():
    assert fn.open_stage_arguments('TMPSYNTH01', 'claude-haiku-4-5-20251001', None) == {
        'infoBank': 'TMPSYNTH01', 'model': 'claude-haiku-4-5-20251001'}


def test_no_pair_sends_the_project_alone():
    assert fn.open_stage_arguments('TMPSYNTH01', None, None) == {'infoBank': 'TMPSYNTH01'}


def test_the_stage_and_its_genesis_are_taken_from_the_answer():
    assert fn.the_stage({'stageSnapshotId': 42, 'parentSnapshotId': 41}) == (42, 41)


@pytest.mark.parametrize('answer, phrase', [
    ('not an object', 'answered no object'),
    ({'errorMessage': '689.064 open_stage: project TMPSYNTH01 has COMMITTED snapshot(s)'}, '689.064'),
    ({'parentSnapshotId': 41}, 'no stageSnapshotId'),
    ({'stageSnapshotId': '42', 'parentSnapshotId': 41}, 'no stageSnapshotId'),
    ({'stageSnapshotId': True, 'parentSnapshotId': 41}, 'no stageSnapshotId'),
    ({'stageSnapshotId': 42}, 'no genesis snapshot'),
    ({'stageSnapshotId': 42, 'parentSnapshotId': None}, 'no genesis snapshot'),
    ({'stageSnapshotId': 42, 'parentSnapshotId': 42}, 'the same id'),
])
def test_an_answer_without_a_stage_and_its_genesis_is_refused(answer, phrase):
    with pytest.raises(ValueError, match=phrase):
        fn.the_stage(answer)
