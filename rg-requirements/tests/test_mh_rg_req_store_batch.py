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
