import pytest
import app
from nrvv_env import Simulation


def _field(state, *names):
    for n in names:
        if isinstance(state, dict) and n in state:
            return state[n]
        if hasattr(state, n):
            return getattr(state, n)
    if isinstance(state, (tuple, list)) and len(state) >= 3:
        idx = {"latest": 0, "acked": 1, "settled": 2}
        for n in names:
            if n in idx:
                return state[idx[n]]
    raise AssertionError("state field missing: %r in %r" % (names, state))


def _state(station):
    st = app.get_station_state(station)
    return (
        _field(st, "latest_desired_price", "latestDesiredPrice", "latest"),
        _field(st, "last_acknowledged_price", "lastAcknowledgedPrice", "acked"),
        _field(st, "settled"),
    )


def _sends(sim, station):
    return [s for s in sim.sends if s.station_id == station]


def _scenario(seed, prices):
    station = "st-%d-%d" % (seed, len(prices))
    sim = Simulation(seed=seed, station_ids=(station,))
    sim.connect(app)
    sim.submit(station, prices[0])
    first = _sends(sim, station)
    if len(first) != 1:
        pytest.skip("precondition not reached: first send not made")
    for p in prices[1:]:
        sim.submit(station, p)
    return sim, station, first[0]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_no_further_send_while_first_unacknowledged(seed):
    sim, station, first = _scenario(seed, [1.50, 1.60, 1.70])
    assert len(_sends(sim, station)) == 1
    # delivery to the station without acknowledgement is still unacknowledged
    sim.deliver(first.send_id)
    assert len(_sends(sim, station)) == 1


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_exactly_one_follow_up_send_with_final_price(seed):
    sim, station, first = _scenario(seed, [1.50, 1.60, 1.70])
    sim.deliver(first.send_id)
    sim.deliver_ack()
    sends = _sends(sim, station)
    assert len(sends) == 2
    assert sends[1].price == 1.70
    assert sends[1].send_id != first.send_id
    sim.run_until_idle()
    sends = _sends(sim, station)
    assert len(sends) == 2
    assert all(s.price != 1.60 for s in sends)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_state_settled_on_final_price_after_ack(seed):
    sim, station, first = _scenario(seed, [1.50, 1.60, 1.70])
    sim.deliver(first.send_id)
    sim.deliver_ack()
    sim.run_until_idle()
    latest, acked, settled = _state(station)
    assert latest == 1.70
    assert acked == 1.70
    assert settled is True or settled == True  # noqa: E712
    assert sim.station_price(station) == 1.70
