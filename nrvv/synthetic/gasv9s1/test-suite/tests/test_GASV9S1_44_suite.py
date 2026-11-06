import importlib

import pytest

import app
import nrvv_env


def _fresh(seed=0, shuffle=False):
    try:
        importlib.reload(app)
    except Exception:
        pass
    sim = nrvv_env.build(seed=seed, clients=("a", "b"), shuffle=shuffle)
    sim.connect(app)
    return sim


def _bound_check(sim):
    """Each displayed number must not exceed the real count at delivery:
    visits delivered so far plus page requests delivered so far (including
    the request itself, which records one visit)."""
    order = sorted((m for m in sim.messages if m.delivered_index is not None),
                   key=lambda m: m.delivered_index)
    real = 0
    for m in order:
        real += 1
        if m.kind == "page_request":
            assert isinstance(m.number, int), "page carries no number"
            assert 0 <= m.number <= real, (m.number, real)


def test_first_request_shows_at_most_one():
    sim = _fresh()
    sim.request_page("a")
    sim.run_until_idle()
    msg = sim.page_replies()[0]
    assert isinstance(msg.number, int)
    assert 0 <= msg.number <= 1


@pytest.mark.parametrize("n", [1, 5, 20])
def test_page_requests_only_never_exceed_request_count(n):
    sim = _fresh()
    for _ in range(n):
        sim.request_page("a")
    sim.run_until_idle()
    nums = [m.number for m in sim.page_replies()]
    assert len(nums) == n
    for i, x in enumerate(nums):
        assert isinstance(x, int)
        assert 0 <= x <= i + 1


def test_visits_then_page_never_exceeds_real_count():
    sim = _fresh()
    for i in range(30):
        sim.visit("a" if i % 2 else "b")
    sim.request_page("a")
    sim.run_until_idle()
    assert len(sim.visits_acknowledged()) == 30
    _bound_check(sim)
    assert sim.page_replies()[0].number <= 31


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_shuffled_mix_never_exceeds_real_count(seed):
    sim = _fresh(seed=seed, shuffle=True)
    for i in range(40):
        if (i * 7 + seed) % 3 == 0:
            sim.request_page("a")
        else:
            sim.visit("b")
    sim.run_until_idle()
    assert len(sim.visits_acknowledged()) == len(sim.visits_sent())
    _bound_check(sim)


def test_shown_numbers_do_not_go_backwards():
    sim = _fresh()
    for i in range(25):
        sim.visit("a")
        sim.request_page("b")
    sim.run_until_idle()
    nums = [m.number for m in sorted(sim.page_replies(), key=lambda m: m.delivered_index)]
    assert nums == sorted(nums)
    _bound_check(sim)


def test_every_page_request_is_answered_with_a_number():
    sim = _fresh()
    for i in range(10):
        sim.request_page("a")
        sim.visit("b")
    sim.run_until_idle()
    assert len(sim.page_replies()) == 10
    assert all(isinstance(m.number, int) for m in sim.page_replies())
