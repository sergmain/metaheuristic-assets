# The batch store's core: taking the collection apart, and deciding what is stored, in which order, against
# which file. The last tests cross the one seam that exists only in production - mh.asset.rg-req-check_1.0
# writes each answer, internal mh.aggregate joins them, this Function takes them apart - by joining exactly as
# mh.aggregate does (AggregateFunction, type text: Collectors.joining("\n\n")) and storing into an in-memory
# RG. No test reaches a real RG, a vault or a dispatcher.

import json
import re

import pytest

import mh_rg_req_check as check
import mh_rg_req_store as store
import mh_rg_req_store_batch as fn


def req(n):
    return {'name': 'R' + str(n), 'content': 'Derby shall do thing ' + str(n) + '.', 'rationale': 'The file says so.'}


def answer(path, *reqs):
    """One branch's answer, written by the real check Function."""
    return check.answer_line(path, json.dumps(list(reqs)))


def collection(*lines):
    """What internal mh.aggregate (type text) makes of the branches' answers."""
    return '\n\n'.join(lines)


@pytest.fixture
def batch(tmp_path):
    return [str(tmp_path / name) for name in ('B.java', 'A.java', 'C.java')]


class InMemoryRg:
    """RG's two create calls, reduced to the two rules the chain depends on: the first only into a project that
    owns no snapshot, a next one only onto the newest committed snapshot. Every create commits a new one."""

    def __init__(self, code='TMPAAAAAAAA'):
        self.code = code
        self.snapshots = []
        self.parents = []
        self.contents = []

    def first(self, body):
        if self.snapshots:
            raise RuntimeError('RG refused the requirement: 04.876.020 the project already owns snapshots')
        return self._commit(body, None)

    def next(self, body):
        if not self.snapshots or body['snapshotId'] != self.snapshots[-1]:
            raise RuntimeError('RG refused the requirement: snapshot ' + str(body['snapshotId'])
                               + ' is not the newest')
        return self._commit(body, body['snapshotId'])

    def _commit(self, body, parent):
        self.contents.append(body['content'])
        self.parents.append(parent)
        self.snapshots.append(100 + len(self.snapshots))
        return self.code + '-' + str(len(self.contents)), self.snapshots[-1]


# ---------------------------------------------------------------------------------------------------
# taking the collection apart

def test_parse_answers_takes_every_line_and_skips_the_blank_ones_between(batch):
    answers = fn.parse_answers(collection(answer(batch[0], req(1), req(2)), answer(batch[1], req(3))) + '\n')

    assert answers == [(batch[0], [req(1), req(2)]), (batch[1], [req(3)])]


def test_parse_answers_of_nothing_is_nothing():
    assert fn.parse_answers('') == []
    assert fn.parse_answers('\n\n \n') == []


def test_parse_answers_refuses_a_line_that_is_not_json_naming_its_number(batch):
    with pytest.raises(ValueError, match='line 3 of the answers is not JSON'):
        fn.parse_answers(collection(answer(batch[0], req(1)), '{broken'))


@pytest.mark.parametrize('line', [
    '[]',
    '{}',
    json.dumps({'sourcePath': ' ', 'requirements': [req(1)]}),
    json.dumps({'sourcePath': 'C:\\x\\A.java', 'requirements': {'content': 'a b c'}}),
    json.dumps({'requirements': [req(1)]}),
])
def test_parse_answers_refuses_a_line_of_the_wrong_shape(line):
    with pytest.raises(ValueError, match=re.escape('line 1 of the answers is not {"sourcePath"')):
        fn.parse_answers(line)


def test_parse_answers_refuses_a_requirement_the_store_would_refuse_naming_the_file(batch):
    line = json.dumps({'sourcePath': batch[0], 'requirements': [req(1), dict(req(2), content='two words')]})

    with pytest.raises(ValueError, match=re.escape('the answer for ' + batch[0] + ' - ') + '.*#2 content'):
        fn.parse_answers(line)


# ---------------------------------------------------------------------------------------------------
# what is stored, in which order

def test_plan_stores_in_the_batchs_order_not_the_collections(batch):
    answers = [(batch[2], [req(5)]), (batch[0], [req(1), req(2)]), (batch[1], [req(3), req(4)])]

    pairs = fn.plan('\n'.join(batch), answers)

    assert pairs == [(batch[0], req(1)), (batch[0], req(2)), (batch[1], req(3)), (batch[1], req(4)),
                     (batch[2], req(5))]


def test_plan_refuses_a_batch_with_a_file_that_has_no_answer(batch):
    answers = [(batch[0], [req(1)]), (batch[2], [req(3)])]

    with pytest.raises(ValueError, match=re.escape('1 of the 3 files have no answer: ' + batch[1])):
        fn.plan('\n'.join(batch), answers)


def test_plan_refuses_a_file_answered_twice(batch):
    answers = [(batch[0], [req(1)]), (batch[1], [req(2)]), (batch[2], [req(3)]), (batch[1], [req(4)])]

    with pytest.raises(ValueError, match=re.escape('answered more than once: ' + batch[1])):
        fn.plan('\n'.join(batch), answers)


def test_plan_refuses_an_answer_for_a_file_outside_the_batch(batch, tmp_path):
    stranger = str(tmp_path / 'Stranger.java')
    answers = [(path, [req(1)]) for path in batch] + [(stranger, [req(2)])]

    with pytest.raises(ValueError, match=re.escape('answered but not in the batch: ' + stranger)):
        fn.plan('\n'.join(batch), answers)


def test_plan_names_ten_missing_files_and_counts_the_rest(tmp_path):
    paths = [str(tmp_path / ('F' + str(i).zfill(2) + '.java')) for i in range(25)]

    with pytest.raises(ValueError) as e:
        fn.plan('\n'.join(paths), [])

    message = str(e.value)
    assert message.startswith('the answers do not cover the batch, nothing was stored: 25 of the 25 files ')
    assert paths[9] in message
    assert paths[10] not in message
    assert message.endswith(', ... (15 more)')


@pytest.mark.parametrize('paths_text, phrase', [
    ('', 'input paths is empty'),
    ('\n \n', 'input paths is empty'),
])
def test_plan_refuses_an_empty_batch(paths_text, phrase):
    with pytest.raises(ValueError, match=phrase):
        fn.plan(paths_text, [])


def test_plan_refuses_a_batch_listing_a_file_twice(batch):
    with pytest.raises(ValueError, match='lists a file more than once'):
        fn.plan('\n'.join(batch + [batch[0]]), [(path, [req(1)]) for path in batch])


def test_sources_text_pairs_each_id_with_its_file(batch):
    pairs = [(batch[0], req(1)), (batch[0], req(2)), (batch[1], req(3))]

    assert fn.sources_text(['TMP-1', 'TMP-2', 'TMP-3'], pairs) == \
        'TMP-1\t' + batch[0] + '\nTMP-2\t' + batch[0] + '\nTMP-3\t' + batch[1]


# ---------------------------------------------------------------------------------------------------
# provenance: a stored requirement's rationale names the file it was derived from

def test_a_stored_rationale_ends_with_the_file_it_was_derived_from(batch):
    pairs = fn.plan('\n'.join(batch), [(batch[0], [req(1)]), (batch[1], [req(2)]), (batch[2], [req(3)])])

    # requirements_to_store is what run() hands the store. Written as a characterization test before it existed:
    # the fallback is exactly what run() stored then - the requirements as CC wrote them
    stored = getattr(fn, 'requirements_to_store', lambda ps: [r for _, r in ps])(pairs)

    assert [r['rationale'] for r in stored] == ['The file says so.\n\nsource: ' + path for path in batch]


# ---------------------------------------------------------------------------------------------------
# one STAGE instead of one snapshot per requirement

class InMemoryRgWithStages:
    """RG's snapshot rules for the store's four calls, the same for every test: a first only into a project that owns
    no snapshot; a STAGE only from a COMMITTED snapshot; a write only into an OPEN STAGE, and only with content; a
    seal only of an OPEN STAGE. The first commits; a write into a STAGE commits nothing; the seal commits it all."""

    def __init__(self, code='TMPAAAAAAAA'):
        self.code = code
        self.snapshots = {}
        self.stored = 0

    def _snapshot(self, status, parent):
        snapshot_id = 100 + len(self.snapshots)
        self.snapshots[snapshot_id] = {'status': status, 'parent': parent, 'contents': [], 'rationales': []}
        return snapshot_id

    def _req(self, snapshot, body):
        if not (body.get('content') or '').strip():
            raise RuntimeError('RG refused the requirement: content is empty')
        snapshot['contents'].append(body['content'])
        snapshot['rationales'].append(body['rationale'])
        self.stored += 1
        return self.code + '-' + str(self.stored)

    def first(self, body):
        if self.snapshots:
            raise RuntimeError('RG refused the requirement: 04.876.020 the project already owns snapshots')
        snapshot_id = self._snapshot('COMMITTED', None)
        return self._req(self.snapshots[snapshot_id], body), snapshot_id

    def open_stage(self, parent):
        if (self.snapshots.get(parent) or {}).get('status') != 'COMMITTED':
            raise RuntimeError('a STAGE forks only from a COMMITTED snapshot, not ' + str(parent))
        return self._snapshot('STAGE', parent)

    def write(self, body):
        snapshot = self.snapshots.get(body['snapshotId'])
        if not snapshot or snapshot['status'] != 'STAGE':
            raise RuntimeError('snapshot ' + str(body['snapshotId']) + ' is not an open STAGE')
        return self._req(snapshot, body)

    def seal(self, stage):
        snapshot = self.snapshots.get(stage)
        if not snapshot or snapshot['status'] != 'STAGE':
            raise RuntimeError('snapshot ' + str(stage) + ' is not an open STAGE')
        snapshot['status'] = 'COMMITTED'
        return stage

    def committed(self):
        return [sid for sid, s in sorted(self.snapshots.items()) if s['status'] == 'COMMITTED']


def store_in_stage(rg, requirements):
    return fn.store_in_one_stage(requirements, rg.first, rg.open_stage, rg.write, rg.seal)


def test_a_whole_batch_is_committed_as_two_snapshots_not_one_per_requirement():
    rg = InMemoryRgWithStages()
    requirements = [req(n) for n in range(1, 482)]

    ids, genesis, sealed = store_in_stage(rg, requirements)

    assert ids == ['TMPAAAAAAAA-' + str(n) for n in range(1, 482)]
    assert rg.committed() == [genesis, sealed], 'the genesis and the sealed STAGE - nothing else'
    assert rg.snapshots[sealed]['parent'] == genesis
    assert rg.snapshots[genesis]['contents'] == [req(1)['content']]
    assert rg.snapshots[sealed]['contents'] == [req(n)['content'] for n in range(2, 482)]


def test_a_single_requirement_opens_no_stage():
    rg = InMemoryRgWithStages()

    ids, genesis, sealed = store_in_stage(rg, [req(1)])

    assert (ids, sealed) == (['TMPAAAAAAAA-1'], None)
    assert rg.committed() == [genesis]


def test_nothing_to_store_is_refused():
    with pytest.raises(ValueError, match='nothing to store'):
        store_in_stage(InMemoryRgWithStages(), [])


def test_a_refused_write_leaves_the_stage_open_and_says_what_is_not_committed():
    rg = InMemoryRgWithStages()
    requirements = [req(1), req(2), dict(req(3), content=' '), req(4)]

    with pytest.raises(RuntimeError) as e:
        store_in_stage(rg, requirements)

    message = str(e.value)
    assert message.startswith('RG refused the requirement: content is empty - committed: TMPAAAAAAAA-1 (snapshot 100)')
    assert 'STAGE 101, which is still open and NOT committed: TMPAAAAAAAA-2' in message
    assert rg.committed() == [100]
    assert rg.snapshots[101]['status'] == 'STAGE'


def test_a_failed_seal_says_the_stage_was_not_sealed():
    rg = InMemoryRgWithStages()

    def refusing_seal(stage):
        raise RuntimeError('mhdg_rg_seal_snapshot failed: 689.030 refused')

    with pytest.raises(RuntimeError) as e:
        fn.store_in_one_stage([req(1), req(2), req(3)], rg.first, rg.open_stage, rg.write, refusing_seal)

    assert str(e.value) == ('mhdg_rg_seal_snapshot failed: 689.030 refused - committed: TMPAAAAAAAA-1 (snapshot 100); '
                            '2 requirement(s) are in STAGE 101, which was NOT sealed')


def test_a_stage_write_answers_the_requirement_id_with_a_null_snapshot():
    assert fn.written_into_stage(200, '{"documentId":7,"message":null,"reqId":"TMP-2","snapshotId":null}') == 'TMP-2'


@pytest.mark.parametrize('status, text, phrase', [
    (200, '{"documentId":null,"message":"04.876.020 ERROR: not a STAGE","reqId":"","snapshotId":null}',
     'no requirement id: .*04.876.020'),
    (200, '{"errorMessages":["610.020 refused"],"reqId":"TMP-2"}', 'RG refused the requirement: 610.020 refused'),
    (200, 'not json', 'not JSON'),
    (401, '', 'rejected the credential'),
    (403, '', 'needs the role ADMIN'),
    (500, 'boom', 'RG answered HTTP 500: boom'),
])
def test_a_stage_write_refuses(status, text, phrase):
    with pytest.raises(RuntimeError, match=phrase):
        fn.written_into_stage(status, text)


def test_the_seam_stores_a_collected_batch_in_one_stage_with_every_rationale_naming_its_file(batch):
    collected = collection(answer(batch[2], req(5)), answer(batch[0], req(1), req(2)), answer(batch[1], req(3)))
    rg = InMemoryRgWithStages()

    pairs = fn.plan('\n'.join(batch), fn.parse_answers(collected))
    ids, genesis, sealed = store_in_stage(rg, fn.requirements_to_store(pairs))

    assert rg.committed() == [genesis, sealed]
    assert rg.snapshots[genesis]['rationales'] == ['The file says so.\n\nsource: ' + batch[0]]
    assert rg.snapshots[sealed]['rationales'] == [
        'The file says so.\n\nsource: ' + batch[0], 'The file says so.\n\nsource: ' + batch[1],
        'The file says so.\n\nsource: ' + batch[2]]
    assert fn.sources_text(ids, pairs).split('\n') == [
        'TMPAAAAAAAA-1\t' + batch[0], 'TMPAAAAAAAA-2\t' + batch[0], 'TMPAAAAAAAA-3\t' + batch[1],
        'TMPAAAAAAAA-4\t' + batch[2]]


# ---------------------------------------------------------------------------------------------------
# the seam: check -> mh.aggregate -> this Function -> the chain

def test_the_batch_is_stored_as_one_chain_in_the_batchs_order_whatever_order_the_answers_arrive_in(batch):
    unusual = {'name': '\u00dcberblick', 'content': 'Derby shall\nnever lose\u2028a transaction.',
               'rationale': 'Kapitel 1.'}
    collected = collection(answer(batch[2], req(5)), answer(batch[0], req(1), unusual), answer(batch[1], req(3)))
    rg = InMemoryRg()

    pairs = fn.plan('\n'.join(batch), fn.parse_answers(collected))
    ids = store.store_all([requirement for _, requirement in pairs], rg.first, rg.next)

    assert ids == ['TMPAAAAAAAA-1', 'TMPAAAAAAAA-2', 'TMPAAAAAAAA-3', 'TMPAAAAAAAA-4']
    assert rg.contents == [req(1)['content'], unusual['content'], req(3)['content'], req(5)['content']]
    assert rg.parents == [None, 100, 101, 102], 'one linear chain: each onto the snapshot the one before committed'
    assert fn.sources_text(ids, pairs).split('\n') == [
        'TMPAAAAAAAA-1\t' + batch[0], 'TMPAAAAAAAA-2\t' + batch[0], 'TMPAAAAAAAA-3\t' + batch[1],
        'TMPAAAAAAAA-4\t' + batch[2]]


def test_a_lost_branch_stores_nothing(batch):
    collected = collection(answer(batch[0], req(1)), answer(batch[2], req(3)))
    rg = InMemoryRg()

    with pytest.raises(ValueError, match='1 of the 3 files have no answer'):
        pairs = fn.plan('\n'.join(batch), fn.parse_answers(collected))
        store.store_all([requirement for _, requirement in pairs], rg.first, rg.next)

    assert rg.contents == []
