import pytest

import app
import nrvv_env


COUNT_KEYS = ("real_count", "count", "visit_count")


def make(seed, shuffle=False):
    sim = nrvv_env.build(seed=seed, clients=("a", "b", "c"), shuffle=shuffle)
    sim.connect(app)
    return sim


def reply_count(msg):
    """Real count carried by a visit acknowledgement, if it exposes one."""
    r = msg.reply
    for k in COUNT_KEYS:
        v = r.get(k) if isinstance(r, dict) else getattr(r, k, None)
        if isinstance(v, int) and not isinstance(v, bool):
            return v
    return None


def acked(msg):
    return msg.reply_index is not None and msg.reply is not None and msg.reply is not False


def send_visits(sim, n, clients=("a", "b", "c")):
    return [sim.visit(clients[i % len(clients)]) for i in range(n)]


def send_repeat(sim, client, visit_id):
    m = sim.visit(client)
    m.payload["visit_id"] = visit_id
    return m


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_each_unique_visit_is_acknowledged(seed):
    sim = make(seed)
    n = 5 + seed
    msgs = send_visits(sim, n)
    sim.run_until_idle()
    assert len(sim.visits_acknowledged()) == n
    assert all(acked(m) for m in msgs)
    ids = {m.payload["visit_id"] for m in msgs}
    assert len(ids) == n


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_real_count_rises_by_one_per_distinct_visit(seed):
    sim = make(seed)
    msgs = send_visits(sim, 6)
    counts = []
    for m in msgs:
        sim.step()
        counts.append(reply_count(m))
    if any(c is None for c in counts):
        pytest.skip("precondition not reached: acknowledgement does not expose the real count")
    for i in range(1, len(counts)):
        assert counts[i] == counts[i - 1] + 1


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_resent_identifier_does_not_change_real_count(seed):
    sim = make(seed)
    first = send_visits(sim, 4)
    sim.run_until_idle()
    base = [reply_count(m) for m in first]
    dups = []
    for i, m in enumerate(first):
        dups.append(send_repeat(sim, "b", m.payload["visit_id"]))
        dups.append(send_repeat(sim, "c", m.payload["visit_id"]))
    sim.run_until_idle()
    assert all(m.reply_index is not None for m in dups)
    if any(c is None for c in base):
        pytest.skip("precondition not reached: acknowledgement does not expose the real count")
    final = base[-1]
    for d in dups:
        c = reply_count(d)
        if c is not None:
            assert c == final
    extra = send_visits(sim, 1)[0]
    sim.run_until_idle()
    assert reply_count(extra) == final + 1


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_shown_number_never_exceeds_distinct_count_after_duplicates(seed):
    sim = make(seed)
    first = send_visits(sim, 3)
    sim.run_until_idle()
    for _ in range(3):
        for m in first:
            send_repeat(sim, "b", m.payload["visit_id"])
    sim.run_until_idle()
    p = sim.request_page("a")
    sim.run_until_idle()
    assert p.number is not None
    # duplicates must not have inflated the number; a page request itself
    # may at most count as one further visit
    assert 0 <= p.number <= 3 + 1


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_interleaved_pages_never_show_more_than_distinct_visits(seed):
    sim = make(seed, shuffle=(seed % 2 == 0))
    visits = send_visits(sim, 6)
    pages = []
    for i, m in enumerate(visits):
        pages.append(sim.request_page("a"))
        send_repeat(sim, "b", m.payload["visit_id"])
    pages.append(sim.request_page("c"))
    sim.run_until_idle()
    assert len(sim.visits_acknowledged()) == 6 + 6
    assert all(p.number is not None for p in pages)
    for p in pages:
        assert 0 <= p.number <= 6 + len(pages)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_interleaved_acknowledged_counts_match_distinct_identifiers(seed):
    sim = make(seed)
    visits = send_visits(sim, 5)
    order = []
    for i, m in enumerate(visits):
        order.append(m)
        sim.request_page("b")
        order.append(send_repeat(sim, "c", m.payload["visit_id"]))
    sim.run_until_idle()
    counts = [reply_count(m) for m in order]
    if any(c is None for c in counts):
        pytest.skip("precondition not reached: acknowledgement does not expose the real count")
    ordered = sorted(order, key=lambda m: m.reply_index)
    seen = set()
    expected = 0
    for m in ordered:
        vid = m.payload["visit_id"]
        if vid not in seen:
            seen.add(vid)
            expected += 1
        assert reply_count(m) == expected
    assert expected == 5


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_shown_number_does_not_decrease_while_visits_arrive(seed):
    sim = make(seed)
    shown = []
    for i in range(6):
        sim.visit("a")
        sim.run_until_idle()
        p = sim.request_page("b")
        sim.run_until_idle()
        shown.append(p.number)
    assert all(n is not None for n in shown)
    assert shown == sorted(shown)
    assert shown[-1] <= 6 + 6
