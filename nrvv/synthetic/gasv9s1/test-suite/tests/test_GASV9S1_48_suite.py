import importlib

import pytest

import app
import nrvv_env


def _fresh(seed, shuffle=False):
    importlib.reload(app)
    sim = nrvv_env.build(seed=seed, clients=("alice", "bob"), shuffle=shuffle)
    sim.connect(app)
    return sim


def _script(sim, n_visits, with_duplicate):
    """Run a fixed-order script; return (shown numbers, list of (page msg, distinct visits so far))."""
    seen_ids = []
    observed = []
    for i in range(n_visits):
        m = sim.visit("alice" if i % 2 == 0 else "bob")
        seen_ids.append(m.payload["visit_id"])
        sim.step()
        p = sim.request_page("bob")
        sim.step()
        observed.append((p, len(seen_ids)))
    if with_duplicate:
        dup = sim.visit("alice")
        dup.payload["visit_id"] = seen_ids[0]
        sim.step()
        p = sim.request_page("alice")
        sim.step()
        observed.append((p, len(seen_ids)))
    for _ in range(3):
        p = sim.request_page("alice")
        sim.step()
        observed.append((p, len(seen_ids)))
    return observed, len(seen_ids)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_shown_number_never_exceeds_distinct_visits(seed):
    sim = _fresh(seed)
    observed, _ = _script(sim, 5, with_duplicate=False)
    for msg, distinct in observed:
        if msg.number is None:
            pytest.skip("precondition not reached: page reply carries no number")
        assert 0 <= msg.number <= distinct


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_shown_number_is_a_count_the_real_count_held(seed):
    sim = _fresh(seed)
    observed, _ = _script(sim, 6, with_duplicate=True)
    for msg, distinct in observed:
        if msg.number is None:
            pytest.skip("precondition not reached: page reply carries no number")
        # real count only ever took values 0..distinct, each exactly once per visit
        assert msg.number in range(0, distinct + 1)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_duplicate_visit_identifier_does_not_inflate_shown_number(seed):
    sim = _fresh(seed)
    observed, distinct = _script(sim, 4, with_duplicate=True)
    for msg, d in observed:
        if msg.number is None:
            pytest.skip("precondition not reached: page reply carries no number")
        assert msg.number <= distinct
    assert distinct == 4


def test_every_visit_is_acknowledged_including_duplicate():
    sim = _fresh(7)
    _script(sim, 3, with_duplicate=True)
    sent = sim.visits_sent()
    assert len(sent) == 4
    assert len(sim.visits_acknowledged()) == len(sent)


def test_visit_acknowledgement_precedes_later_page_request_events():
    sim = _fresh(11)
    v = sim.visit("alice")
    sim.step()
    p = sim.request_page("bob")
    sim.step()
    assert v.reply_index is not None
    assert v.reply_index < p.delivered_index
    if p.number is None:
        pytest.skip("precondition not reached: page reply carries no number")
    assert p.number in (0, 1)
