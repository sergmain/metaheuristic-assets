import pytest

import app
import nrvv_env

_READER_NAMES = ("real_count", "get_real_count", "read_real_count",
                 "real_visit_count", "get_real_visit_count",
                 "current_real_count", "read_count")

SEEDS = (1, 2, 3)


def _direct_reader():
    for n in _READER_NAMES:
        v = getattr(app, n, None)
        if callable(v):
            return v
        if isinstance(v, int) and not isinstance(v, bool):
            return lambda n=n: getattr(app, n)
    return None


def _need_reader():
    r = _direct_reader()
    if r is None:
        pytest.skip("precondition not reached: real count cannot be read directly through nrvv_env")
    return r


def _fire(seed, n, shuffle=True):
    sim = nrvv_env.build(seed=seed, clients=["c%d" % i for i in range(n)], shuffle=shuffle)
    sim.connect(app)
    for i in range(n):
        sim.visit("c%d" % i)
    return sim


@pytest.mark.parametrize("seed", SEEDS)
def test_all_concurrent_visits_acknowledged_with_distinct_ids(seed):
    n = 12
    sim = _fire(seed, n)
    assert len(sim.in_flight()) == n
    sim.run_until_idle()
    assert len(sim.visits_acknowledged()) == n
    ids = [m.payload["visit_id"] for m in sim.visits_sent()]
    assert len(set(ids)) == n


@pytest.mark.parametrize("seed", SEEDS)
def test_real_count_equals_c_plus_n_after_all_acknowledged(seed):
    reader = _need_reader()
    c_sim = nrvv_env.build(seed=seed + 100, clients=["pre"])
    c_sim.connect(app)
    for _ in range(3):
        c_sim.visit("pre")
    c_sim.run_until_idle()
    c = reader()
    n = 15
    sim = _fire(seed, n)
    sim.run_until_idle()
    assert len(sim.visits_acknowledged()) == n
    assert reader() == c + n


@pytest.mark.parametrize("seed", SEEDS)
def test_real_count_grows_by_one_after_each_acknowledgement(seed):
    reader = _need_reader()
    c = reader()
    n = 10
    sim = _fire(seed, n)
    k = 0
    while not sim.idle():
        msg = sim.step()
        assert msg.reply_index is not None
        k += 1
        assert reader() == c + k


@pytest.mark.parametrize("seed", SEEDS)
def test_shown_number_never_exceeds_real_count_during_concurrent_visits(seed):
    n = 8
    sim = nrvv_env.build(seed=seed, clients=["v%d" % i for i in range(n)] + ["p"], shuffle=True)
    sim.connect(app)
    for i in range(n):
        sim.visit("v%d" % i)
    sim.run_until_idle()
    sim.request_page("p")
    sim.run_until_idle()
    pages = sim.page_replies()
    assert len(pages) == 1
    shown = pages[0].number
    assert shown is not None
    reader = _direct_reader()
    if reader is not None:
        assert shown <= reader()
