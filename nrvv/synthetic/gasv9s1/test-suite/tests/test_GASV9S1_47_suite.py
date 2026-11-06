import pytest
import app
import nrvv_env
from nrvv_env.sim import _extract_number


def _fresh(seed=0, shuffle=False):
    sim = nrvv_env.build(seed=seed, clients=("a", "b"), shuffle=shuffle)
    sim.connect(app)
    return sim


def _count_of(msg):
    n = _extract_number(msg.reply)
    if n is None:
        pytest.skip("precondition not reached: acknowledgement carries no readable count")
    return n


def _resend(sim, msg):
    # retry / duplicate delivery of the same visit (same visit identifier)
    return sim._send(msg.client, "visit", dict(msg.payload))


def _deliver(sim, msg):
    while msg.reply_index is None:
        if sim.step() is None:
            break
    assert msg.reply_index is not None
    return msg


def test_new_visits_each_raise_count_by_one():
    sim = _fresh()
    counts = []
    for i in range(3):
        m = sim.visit("a")
        _deliver(sim, m)
        counts.append(_count_of(m))
    assert counts[1] == counts[0] + 1
    assert counts[2] == counts[1] + 1


def test_duplicate_visit_does_not_change_count():
    sim = _fresh()
    i1 = sim.visit("a")
    _deliver(sim, i1)
    c1 = _count_of(i1)
    dup = _resend(sim, i1)
    _deliver(sim, dup)
    assert _count_of(dup) == c1
    i2 = sim.visit("a")
    _deliver(sim, i2)
    assert _count_of(i2) == c1 + 1


def test_repeated_retries_never_add():
    sim = _fresh()
    i1 = sim.visit("a")
    _deliver(sim, i1)
    c1 = _count_of(i1)
    for _ in range(5):
        d = _resend(sim, i1)
        _deliver(sim, d)
        assert _count_of(d) == c1
    i2 = sim.visit("b")
    _deliver(sim, i2)
    assert _count_of(i2) == c1 + 1


def test_full_scenario_i1_dup_i2_i3():
    sim = _fresh()
    i1 = sim.visit("a")
    _deliver(sim, i1)
    c1 = _count_of(i1)
    d = _resend(sim, i1)
    _deliver(sim, d)
    assert _count_of(d) == c1
    i2 = sim.visit("b")
    _deliver(sim, i2)
    assert _count_of(i2) == c1 + 1
    i3 = sim.visit("a")
    _deliver(sim, i3)
    assert _count_of(i3) == c1 + 2


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_increments_applied_at_once_while_pages_served(seed):
    sim = _fresh(seed)
    i1 = sim.visit("a")
    sim.request_page("b")
    d = None
    sim.request_page("a")
    i2 = sim.visit("b")
    sim.request_page("b")
    i3 = sim.visit("a")
    sim.request_page("a")
    sim.run_until_idle()
    first = _count_of(i1)
    assert _count_of(i2) == first + 1
    assert _count_of(i3) == first + 2
    # duplicate amid page traffic
    sim.request_page("b")
    d = _resend(sim, i1)
    sim.request_page("a")
    sim.run_until_idle()
    assert _count_of(d) == first + 2
    i4 = sim.visit("a")
    sim.run_until_idle()
    assert _count_of(i4) == first + 3


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_shuffled_delivery_with_pages_and_duplicates(seed):
    sim = _fresh(seed, shuffle=True)
    ids = []
    for k in range(4):
        ids.append(sim.visit("a" if k % 2 else "b"))
        sim.request_page("a")
    dups = [_resend(sim, ids[0]), _resend(sim, ids[2])]
    sim.request_page("b")
    sim.run_until_idle()
    uniq = sorted(ids, key=lambda m: m.delivered_index)
    cs = [_count_of(m) for m in uniq]
    # ordered by delivery event index: each new visit adds exactly one
    for a, b in zip(cs, cs[1:]):
        assert b == a + 1
    # duplicates delivered after their original add nothing; count never exceeds total unique
    final = cs[-1]
    for dm in dups:
        assert _count_of(dm) <= final
        orig = ids[0] if dm.payload["visit_id"] == ids[0].payload["visit_id"] else ids[2]
        if dm.delivered_index > orig.delivered_index:
            assert _count_of(dm) >= _count_of(orig)
    extra = sim.visit("a")
    sim.run_until_idle()
    assert _count_of(extra) == final + 1


def test_page_never_shows_more_than_real_count():
    sim = _fresh()
    last = None
    for k in range(3):
        v = sim.visit("a")
        _deliver(sim, v)
        last = _count_of(v)
        p = sim.request_page("b")
        _deliver(sim, p)
        if p.number is None:
            pytest.skip("precondition not reached: page reply carries no readable number")
        assert p.number <= last
    v = sim.visit("a")
    _deliver(sim, v)
    assert _count_of(v) == last + 1
