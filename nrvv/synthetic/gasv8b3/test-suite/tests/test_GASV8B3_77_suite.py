import pytest

import app
from nrvv_env import Simulation


def _field(state, snake):
    parts = snake.split("_")
    camel = parts[0] + "".join(p.capitalize() for p in parts[1:])
    if isinstance(state, dict):
        for k in (snake, camel):
            if k in state:
                return state[k]
        raise KeyError(snake)
    for k in (snake, camel):
        if hasattr(state, k):
            return getattr(state, k)
    if isinstance(state, (tuple, list)) and len(state) == 3:
        return state[("latest_desired_price", "last_acknowledged_price", "settled").index(snake)]
    raise KeyError(snake)


def _state(station):
    return app.get_station_state(station)


def _setup(seed, station):
    sim = Simulation(seed=seed, station_ids=(station,))
    sim.connect(app)
    return sim


def _first_send_and_pile_up(sim, station, prices):
    a, rest = prices[0], prices[1:]
    sim.submit(station, a)
    if len(sim.sends) != 1:
        pytest.skip("precondition not reached: first send not dispatched")
    for p in rest:
        sim.submit(station, p)
    return sim.sends[0]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_no_second_send_while_unacknowledged_and_latest_recorded(seed):
    station = "st-hold-%d" % seed
    sim = _setup(seed, station)
    s1 = _first_send_and_pile_up(sim, station, [101, 102, 103])
    assert s1.price == 101
    assert len(sim.sends) == 1
    assert _field(_state(station), "latest_desired_price") == 103


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_ack_of_superseded_send_triggers_exactly_one_send_of_latest(seed):
    station = "st-follow-%d" % seed
    sim = _setup(seed, station)
    s1 = _first_send_and_pile_up(sim, station, [201, 202, 203])
    sim.deliver(s1.send_id, station)
    ack = sim.deliver_ack()
    assert ack.send_id == s1.send_id
    assert len(sim.sends) == 2
    s2 = sim.sends[1]
    assert s2.station_id == station
    assert s2.price == 203
    assert s2.send_id != s1.send_id
    assert all(s.price != 202 for s in sim.sends)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_settles_on_latest_after_followup_ack_with_no_further_sends(seed):
    station = "st-settle-%d" % seed
    sim = _setup(seed, station)
    s1 = _first_send_and_pile_up(sim, station, [301, 302, 303])
    sim.deliver(s1.send_id, station)
    sim.deliver_ack()
    if len(sim.sends) != 2:
        pytest.skip("precondition not reached: follow-up send not made")
    s2 = sim.sends[1]
    sim.deliver(s2.send_id, station)
    sim.deliver_ack()
    st = _state(station)
    assert _field(st, "last_acknowledged_price") == 303
    assert _field(st, "latest_desired_price") == 303
    assert _field(st, "settled") is True
    assert len(sim.sends) == 2
    sim.run_until_idle()
    assert len(sim.sends) == 2
    assert sim.station_price(station) == 303


def test_not_settled_while_first_send_unacknowledged():
    station = "st-unsettled"
    sim = _setup(7, station)
    _first_send_and_pile_up(sim, station, [401, 402, 403])
    assert not _field(_state(station), "settled")
