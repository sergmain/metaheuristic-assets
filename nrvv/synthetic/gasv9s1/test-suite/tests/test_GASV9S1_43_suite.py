import pytest

import app
import nrvv_env


def _setup(seed, shuffle=False):
    sim = nrvv_env.build(seed=seed, clients=("a", "b"), shuffle=shuffle)
    sim.connect(app)
    return sim


def _page(sim, client="a"):
    sim.request_page(client)
    sim.run_until_idle()
    msg = sim.page_replies()[-1]
    return msg.number


def test_page_after_visits_never_exceeds_real_count():
    for seed in (1, 2, 3):
        sim = _setup(seed)
        n = 5 + seed
        for _ in range(n):
            sim.visit("a")
        sim.run_until_idle()
        assert len(sim.visits_acknowledged()) == n
        shown = _page(sim)
        assert shown is not None
        assert 0 <= shown <= n


def test_first_request_serves_value_real_count_held():
    # a value the real count held is any integer between 0 and N
    sim = _setup(7)
    for _ in range(4):
        sim.visit("a")
    sim.run_until_idle()
    shown = _page(sim)
    assert shown is not None and 0 <= shown <= 4


def test_served_numbers_are_monotonic_and_bounded_with_more_visits():
    for seed in (11, 12):
        sim = _setup(seed)
        for _ in range(3):
            sim.visit("a")
        sim.run_until_idle()
        first = _page(sim)
        for _ in range(6):
            sim.visit("b")
        sim.run_until_idle()
        second = _page(sim, "b")
        assert first is not None and second is not None
        assert first <= second <= 9
        assert first <= 3


def test_repeated_requests_never_show_more_than_visits_recorded_so_far():
    sim = _setup(21)
    recorded = 0
    last = 0
    for i in range(8):
        sim.visit("a")
        recorded += 1
        sim.run_until_idle()
        shown = _page(sim)
        assert shown is not None
        assert last <= shown <= recorded
        last = shown


def test_no_visits_shows_zero():
    sim = _setup(5)
    shown = _page(sim)
    assert shown == 0


def test_shuffled_delivery_still_bounded():
    for seed in (31, 32, 33):
        sim = _setup(seed, shuffle=True)
        for _ in range(6):
            sim.visit("a")
        sim.request_page("b")
        sim.run_until_idle()
        pages = sim.page_replies()
        assert len(pages) == 1
        delivered_visits_before = [
            m for m in sim.visits_sent()
            if m.delivered_index is not None and m.delivered_index < pages[0].delivered_index
        ]
        assert 0 <= pages[0].number <= len(delivered_visits_before)
