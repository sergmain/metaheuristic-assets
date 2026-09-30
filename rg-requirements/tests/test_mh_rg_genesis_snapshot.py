# Which snapshot is the genesis: decided from what the RG MCP tool mhdg_rg_list_snapshots answers. The listings keep
# the shape the tool answered on this installation (2026-09-30, project TMPVG956AFJ: infoBank, snapshots[{snapshotId,
# parentSnapshotId, status, statusName, ...}], errorMessage); the values are synthetic.

import pytest

import mh_rg_genesis_snapshot as fn


def snapshot(snapshot_id, status_name, parent=None):
    return {'snapshotId': snapshot_id, 'parentSnapshotId': parent, 'status': 1 if status_name == 'COMMITTED' else 0,
            'statusName': status_name, 'createdAt': 1790788427091, 'committedAt': None, 'username': 'pipeline-run',
            'tags': [], 'description': None, 'model': 'claude-sonnet-4-6', 'effort': 'medium'}


def listing(*snapshots, error=None):
    return {'infoBank': 'TMPSYNTH01', 'snapshots': list(snapshots), 'errorMessage': error}


def test_the_one_committed_parentless_snapshot_is_the_genesis():
    assert fn.the_genesis(listing(snapshot(3, 'COMMITTED'))) == 3


@pytest.mark.parametrize('answer, phrase', [
    (listing(), 'found 0'),
    (listing(snapshot(3, 'COMMITTED'), snapshot(4, 'STAGE', 3)), 'found 2: 3 COMMITTED, 4 STAGE'),
    (listing(snapshot(3, 'STAGE')), 'not a COMMITTED genesis'),
    (listing(snapshot(5, 'COMMITTED', 3)), 'not a COMMITTED genesis'),
    (listing(error='Project not found: TMPSYNTH01'), 'Project not found: TMPSYNTH01'),
    ({'infoBank': 'TMPSYNTH01'}, 'no snapshot list'),
    ('not an object', 'answered no object'),
])
def test_anything_but_one_committed_genesis_is_refused_naming_what_was_found(answer, phrase):
    with pytest.raises(ValueError, match=phrase):
        fn.the_genesis(answer)
