import pytest
import app
import nrvv_env
from nrvv_env import Simulation


def _field(state, snake):
    parts = snake.split("_")
    camel = parts[0] + "".join(p.capitalize() for p in parts[1:])
    if isinstance(state, dict):
        for k in (snake, camel):
            if k in state:
                return state[k]
        raise AssertionError("missing field %s in %r" % (snake, state))
    for k in (snake, camel):
        if hasattr(state, k):
            return getattr(state, k)
    raise AssertionError("missing field %s in %r" % (snake, state))


def _sends_for(sim, station):
    return [s for s in sim.sends if s.station_id == station]


def _scenario(seed, station, prices):
    p1, p2, p3 = prices
    sim = Simulation(seed=seed, station_ids=(station,))
    sim.connect(app)
    sim.submit(station, p1)
    sends = _sends_for(sim, station)
    assert len(sends) == 1
    assert sends[0].price == p1
    s1 = sends[0].send_id

    sim.submit(station, p2)
    sim.submit(station, p3)
    assert len(_sends_for(sim, station)) == 1

    sim.deliver(s1, station)
    sim.deliver_ack()
    sends = _sends_for(sim, station)
    assert len(sends) == 2
    second = sends[1]
    assert second.price == p3
    assert second.send_id != s1
    return sim, second


def test_no_send_while_first_unacknowledged_and_p3_follows():
    _scenario(1, "st-a", (100, 110, 120))


def test_p2_is_never_sent():
    sim, _ = _scenario(2, "st-b", (200, 210, 220))
    sim.run_until_idle()
    prices = [s.price for s in _sends_for(sim, "st-b")]
    assert 210 not in prices


def test_final_state_settled_on_p3():
    station = "st-c"
    sim, second = _scenario(3, station, (300, 310, 320))
    sim.deliver(second.send_id, station)
    sim.deliver_ack()
    state = app.get_station_state(station)
    assert _field(state, "latest_desired_price") == 320
    assert _field(state, "last_acknowledged_price") == 320
    assert _field(state, "settled") is True
    assert len(_sends_for(sim, station)) == 2


@pytest.mark.parametrize("seed", [5, 6, 7])
def test_exactly_one_new_send_after_ack_across_seeds(seed):
    station = "st-d%d" % seed
    sim, second = _scenario(seed, station, (1, 2, 3))
    assert len(_sends_for(sim, station)) == 2
    sim.run_until_idle()
    assert len(_sends_for(sim, station)) == 2
    state = app.get_station_state(station)
    assert _field(state, "settled") is True
    assert _field(state, "latest_desired_price") == 3
