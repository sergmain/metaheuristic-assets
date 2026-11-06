import pytest

import app
import nrvv_env


def _get(state, key):
    if isinstance(state, dict):
        return state[key]
    return getattr(state, key)


def _drive(sim, station, max_rounds=200):
    """Run transport to idle, advancing the clock between rounds so retries can happen."""
    for _ in range(max_rounds):
        sim.run_until_idle()
        state = app.get_station_state(station)
        if _get(state, "settled") and sim.idle():
            return state
        sim.advance(1000.0)
    sim.run_until_idle()
    return app.get_station_state(station)


def _scenario(seed, ordering, arrival, p1=10.0, p2=20.0, station="S1"):
    sim = nrvv_env.Simulation(seed=seed, ordering=ordering, start_time=100.0)
    sim.connect(app)
    if arrival is not None:
        sim.set_arrival_order(arrival)
    sim.submit(station, p1)
    sim.advance(1.0)
    sim.submit(station, p2)
    state = _drive(sim, station)
    return sim, state


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_newer_price_wins_when_older_send_arrives_last(seed):
    p1, p2 = 10.0, 20.0
    sim, state = _scenario(seed, "fifo", [1, 0], p1, p2)
    assert _get(state, "latest_desired_price") == p2
    assert _get(state, "last_acknowledged_price") == p2
    assert _get(state, "settled") is True
    assert sim.station_price("S1") == p2
    assert sim.station_price("S1") != p1


@pytest.mark.parametrize("seed", [5, 6, 7, 8])
def test_station_settles_on_latest_price_with_random_arrival(seed):
    p1, p2 = 11.5, 22.5
    sim, state = _scenario(seed, "random", [1, 0, 2, 3], p1, p2)
    assert _get(state, "latest_desired_price") == p2
    assert _get(state, "last_acknowledged_price") == p2
    assert _get(state, "settled") is True
    assert sim.station_price("S1") == p2


def test_last_arrival_at_station_is_latest_price():
    sim, state = _scenario(4, "fifo", [1, 0], 3.0, 4.0)
    assert _get(state, "settled") is True
    applied = sim.station_applied.get("S1", [])
    assert applied, "no delivery reached the station"
    last = max(applied, key=lambda a: a[0])
    assert last[2] == 4.0
