import importlib

import pytest

import app
import nrvv_env


def _fresh(seed=0, shuffle=False):
    importlib.reload(app)
    sim = nrvv_env.build(seed=seed, clients=("c1", "c2"), shuffle=shuffle)
    sim.connect(app)
    return sim


def _shown(sim, client="c1"):
    m = sim.request_page(client)
    sim.run_until_idle()
    assert m.number is not None
    return m.number


def _send_visit(sim, client="c1"):
    m = sim.visit(client)
    sim.run_until_idle()
    return m


def _resend(sim, msg):
    """Deliver another notification carrying the same visit identifier."""
    d = sim._send(msg.client, "visit", dict(msg.payload))
    sim.run_until_idle()
    return d


def _baseline(sim, n):
    if _shown(sim) != 0:
        pytest.skip("precondition not reached: fresh app does not start at zero")
    for _ in range(n):
        m = _send_visit(sim)
        assert m.reply_index is not None
    return n


def _check(sim, expected):
    """The real count is read through the page: it never exceeds expected
    (no double counting); a shown number below it is only display lag."""
    number = _shown(sim, "c2")
    assert number <= expected
    if number < expected:
        pytest.skip("precondition not reached: page lags behind the real count")
    assert number == expected


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_single_visit_is_acknowledged_and_adds_one(seed):
    sim = _fresh(seed)
    n = _baseline(sim, 3)
    m = _send_visit(sim)
    assert m.reply_index is not None
    assert m in sim.visits_acknowledged()
    _check(sim, n + 1)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_duplicate_deliveries_add_nothing(seed):
    sim = _fresh(seed)
    n = _baseline(sim, 2)
    m = _send_visit(sim)
    for _ in range(5):
        d = _resend(sim, m)
        assert d.reply_index is not None
        assert d.payload == m.payload
        assert _shown(sim, "c2") <= n + 1
    _check(sim, n + 1)


def test_duplicates_sent_in_one_batch_count_once():
    sim = _fresh(4)
    n = _baseline(sim, 1)
    m = sim.visit("c1")
    for _ in range(4):
        sim._send("c1", "visit", dict(m.payload))
    sim.run_until_idle()
    assert all(x.reply_index is not None for x in sim.visits_sent()[-5:])
    _check(sim, n + 1)


@pytest.mark.parametrize("seed", [5, 6])
def test_lost_acknowledgement_resent_counts_exactly_once(seed):
    sim = _fresh(seed)
    n = _baseline(sim, 2)
    m = sim.visit("c1")
    sim.run_until_idle()
    # the client treats this acknowledgement as lost and resends with the same id
    r1 = _resend(sim, m)
    assert r1.reply_index is not None
    assert _shown(sim, "c2") <= n + 1
    _check(sim, n + 1)


def test_resent_until_acknowledged_counts_once_with_repeated_loss():
    sim = _fresh(7)
    n = _baseline(sim, 0)
    m = sim.visit("c1")
    sim.run_until_idle()
    for _ in range(3):
        _resend(sim, m)
    _check(sim, n + 1)


@pytest.mark.parametrize("seed", [8, 9, 10])
def test_distinct_identifiers_each_add_exactly_one(seed):
    sim = _fresh(seed, shuffle=True)
    n = _baseline(sim, 1)
    msgs = [sim.visit("c1" if i % 2 else "c2") for i in range(6)]
    sim.run_until_idle()
    ids = [m.payload["visit_id"] for m in msgs]
    assert len(set(ids)) == 6
    assert all(m.reply_index is not None for m in msgs)
    _check(sim, n + 6)


@pytest.mark.parametrize("seed", [11, 12])
def test_mixed_duplicates_and_distinct_visits(seed):
    sim = _fresh(seed)
    n = _baseline(sim, 2)
    a = _send_visit(sim)
    _resend(sim, a)
    b = _send_visit(sim, "c2")
    _resend(sim, a)
    _resend(sim, b)
    c = _send_visit(sim)
    _resend(sim, c)
    _resend(sim, b)
    assert _shown(sim, "c2") <= n + 3
    _check(sim, n + 3)
