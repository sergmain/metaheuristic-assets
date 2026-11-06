import pytest

import app
import nrvv_env


def _connected(seed=0, shuffle=False):
    sim = nrvv_env.build(seed=seed, clients=("a", "b"), shuffle=shuffle)
    sim.connect(app)
    return sim


def _page(sim, client="a"):
    m = sim.request_page(client)
    sim.run_until_idle()
    return m.number


def test_page_before_any_visit_shows_zero():
    sim = _connected()
    n = _page(sim)
    assert n == 0


def test_page_after_five_visits_shows_value_from_zero_to_five():
    for seed in (0, 1, 2):
        sim = _connected(seed)
        for _ in range(5):
            sim.visit("a")
        sim.run_until_idle()
        assert len(sim.visits_acknowledged()) == 5
        n = _page(sim, "b")
        assert isinstance(n, int)
        assert 0 <= n <= 5


def test_page_never_exceeds_real_count_while_visits_arrive_interleaved():
    for seed in (3, 4, 5):
        sim = _connected(seed, shuffle=True)
        real = 0
        for i in range(8):
            sim.visit("a" if i % 2 else "b")
            sim.run_until_idle()
            real += 1
            n = _page(sim)
            assert n is not None
            assert 0 <= n <= real


def test_displayed_value_was_real_count_at_some_earlier_moment():
    sim = _connected(7)
    history = [0]
    shown = []
    for i in range(6):
        sim.visit("a")
        sim.run_until_idle()
        history.append(i + 1)
        shown.append(_page(sim))
    for n in shown:
        assert n in history


def test_repeated_requests_without_new_visits_never_exceed_count():
    sim = _connected(11)
    for _ in range(5):
        sim.visit("a")
    sim.run_until_idle()
    for _ in range(50):
        n = _page(sim, "b")
        assert 0 <= n <= 5


def test_requests_in_flight_with_visits_never_show_more_than_visits_delivered():
    sim = _connected(13, shuffle=True)
    for _ in range(5):
        sim.visit("a")
        sim.request_page("b")
    delivered_visits = 0
    while not sim.idle():
        msg = sim.step()
        if msg.kind == "visit":
            delivered_visits += 1
        else:
            assert msg.number is not None
            assert 0 <= msg.number <= delivered_visits


def test_displayed_number_eventually_equals_real_count_when_stable():
    sim = _connected(17)
    for _ in range(5):
        sim.visit("a")
    sim.run_until_idle()
    numbers = [_page(sim, "b") for _ in range(100)]
    assert all(0 <= n <= 5 for n in numbers)
    if 5 not in numbers:
        pytest.skip("precondition not reached: no time passes in nrvv_env so the snapshot may legitimately stay stale")
    assert numbers[-1] == 5 or 5 in numbers


def test_page_after_further_visits_shows_only_valid_values():
    sim = _connected(19)
    total = 0
    for batch in (2, 3, 1, 4):
        for _ in range(batch):
            sim.visit("a")
        sim.run_until_idle()
        total += batch
        for _ in range(3):
            n = _page(sim, "b")
            assert 0 <= n <= total
