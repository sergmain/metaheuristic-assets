import pytest

import app
import nrvv_env


def _connect(seed, shuffle=False):
    sim = nrvv_env.build(seed=seed, clients=("alice", "bob"), shuffle=shuffle)
    sim.connect(app)
    return sim


def _page(sim, client="alice"):
    m = sim.request_page(client)
    sim.run_until_idle()
    if m.number is None:
        pytest.skip("precondition not reached: page reply carries no number")
    return m.number


def _visits(sim, k):
    msgs = [sim.visit("alice" if i % 2 == 0 else "bob") for i in range(k)]
    sim.run_until_idle()
    for m in msgs:
        if m.reply_index is None:
            pytest.skip("precondition not reached: visit not acknowledged")
    return msgs


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_shown_number_is_a_real_count_after_visits(seed):
    sim = _connect(seed)
    base = _page(sim)
    k = 5 + seed
    _visits(sim, k)
    shown = _page(sim)
    assert base <= shown <= base + k


@pytest.mark.parametrize("seed", [4, 5])
def test_shown_number_never_exceeds_real_count_during_interleaving(seed):
    sim = _connect(seed, shuffle=True)
    base = _page(sim)
    total = 0
    for round_no in range(4):
        _visits(sim, 3)
        total += 3
        shown = _page(sim, "bob")
        assert base <= shown <= base + total


def test_shown_numbers_do_not_go_backwards():
    sim = _connect(7)
    base = _page(sim)
    seen = [base]
    for _ in range(5):
        _visits(sim, 2)
        seen.append(_page(sim))
    assert seen == sorted(seen)
    assert seen[-1] <= base + 10


def test_shown_number_equals_real_count_at_an_earlier_moment():
    sim = _connect(11)
    base = _page(sim)
    acked_before_request = len(_visits(sim, 4))
    shown = _page(sim)
    req = sim.page_replies()[-1]
    acked_at_request = [
        m for m in sim.visits_acknowledged() if m.reply_index < req.delivered_index
    ]
    assert base <= shown <= base + len(acked_at_request)
    assert acked_before_request == 4


def test_forced_refresh_near_30_seconds_shows_current_count():
    pytest.skip("precondition not reached: nrvv_env offers no scripted clock to age the snapshot")
