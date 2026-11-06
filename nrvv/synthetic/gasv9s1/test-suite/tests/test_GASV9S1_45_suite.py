import pytest
import app
import nrvv_env

_REAL_NAMES = ("real_count", "get_real_count", "real_visit_count",
               "read_real_count", "get_real_visit_count", "visit_count_real")


def _real_count():
    for n in _REAL_NAMES:
        v = getattr(app, n, None)
        if v is None:
            continue
        if callable(v):
            try:
                v = v()
            except TypeError:
                continue
        if isinstance(v, int) and not isinstance(v, bool):
            return v
    return None


def _run(seed, n, shuffle, clients=("a", "b", "c"), pages=False):
    sim = nrvv_env.build(seed=seed, clients=clients, shuffle=shuffle)
    sim.connect(app)
    start = _real_count()
    sent = []
    for i in range(n):
        c = clients[i % len(clients)]
        if pages and i % 3 == 0:
            sim.request_page(c)
        sent.append(sim.visit(c))
        if pages and i % 5 == 0:
            sim.request_page(clients[(i + 1) % len(clients)])
    sim.run_until_idle()
    return sim, sent, start


def _check_acks(sim, sent):
    assert len(sent) == len({m.payload["visit_id"] for m in sent})
    for m in sent:
        assert m.reply_index is not None
        assert m.reply is not None and m.reply is not False
    assert len(sim.visits_acknowledged()) == len(sent)
    for m in sent:
        assert m.sent_index < m.delivered_index < m.reply_index


def _check_delta(start, n):
    end = _real_count()
    if start is None or end is None:
        pytest.skip("precondition not reached: real count not readable")
    assert end - start == n


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_ordered_visits_all_acknowledged(seed):
    sim, sent, _ = _run(seed, 20, False)
    _check_acks(sim, sent)


@pytest.mark.parametrize("seed", [4, 5, 6])
def test_interleaved_visits_all_acknowledged_once(seed):
    sim, sent, _ = _run(seed, 30, True)
    _check_acks(sim, sent)
    delivered = [m for m in sim.messages if m.kind == "visit"]
    assert len({m.delivered_index for m in delivered}) == 30


def test_real_count_rises_by_exactly_n_ordered():
    sim, sent, start = _run(11, 20, False)
    _check_acks(sim, sent)
    _check_delta(start, 20)


@pytest.mark.parametrize("seed", [21, 22, 23])
def test_real_count_rises_by_exactly_n_interleaved(seed):
    sim, sent, start = _run(seed, 37, True)
    _check_acks(sim, sent)
    _check_delta(start, 37)


@pytest.mark.parametrize("seed", [31, 32])
def test_count_independent_of_page_requests(seed):
    sim, sent, start = _run(seed, 25, True, pages=True)
    _check_acks(sim, sent)
    _check_delta(start, 25)


def test_displayed_number_never_exceeds_real_count():
    sim, sent, start = _run(41, 24, True, pages=True)
    _check_acks(sim, sent)
    if start is None:
        pytest.skip("precondition not reached: real count not readable")
    end = _real_count()
    assert end - start == 24
    for m in sim.page_replies():
        assert m.number is not None
        assert m.number <= end


def test_two_batches_each_add_exactly_n():
    sim, sent, start = _run(51, 20, True)
    _check_acks(sim, sent)
    _check_delta(start, 20)
    mid = _real_count()
    sim2 = nrvv_env.build(seed=52, clients=("x", "y"), shuffle=True)
    sim2.connect(app)
    sent2 = [sim2.visit("xy"[i % 2]) for i in range(22)]
    sim2.run_until_idle()
    _check_acks(sim2, sent2)
    if mid is None:
        pytest.skip("precondition not reached: real count not readable")
    assert _real_count() - mid == 22
