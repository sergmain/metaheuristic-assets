import pytest

import app
from nrvv_env import Simulation


def _field(state, *names):
    for n in names:
        if isinstance(state, dict):
            if n in state:
                return state[n]
        elif hasattr(state, n):
            return getattr(state, n)
    raise AssertionError("state lacks any of %r: %r" % (names, state))


def _accepted(result):
    if isinstance(result, str):
        return result.lower() == "accepted"
    return bool(result)


def _scenario(seed, station="S1", prices=(100, 110, 120)):
    sim = Simulation(seed=seed, station_ids=[station]).connect(app)
    p1, p2, p3 = prices
    r1 = sim.submit(station, p1)
    assert _accepted(r1)
    if not sim.in_flight:
        pytest.skip("precondition not reached: first send not in flight after submit")
    r2 = sim.submit(station, p2)
    r3 = sim.submit(station, p3)
    assert _accepted(r2)
    assert _accepted(r3)
    # acknowledge each send in turn until nothing is in flight
    guard = 0
    while sim.in_flight or sim.pending_acks:
        if sim.pending_acks:
            sim.deliver_ack()
        else:
            sim.deliver(sim.in_flight[0].send_id)
        guard += 1
        assert guard < 1000
    return sim


@pytest.mark.parametrize("seed", [0, 1, 7, 42])
def test_intermediate_price_p2_is_never_sent(seed):
    sim = _scenario(seed)
    sent = [s.price for s in sim.sends if s.station_id == "S1"]
    assert 110 not in sent
    assert sent[0] == 100


@pytest.mark.parametrize("seed", [0, 1, 7, 42])
def test_last_price_sent_is_p3(seed):
    sim = _scenario(seed)
    sent = [s.price for s in sorted(sim.sends, key=lambda r: r.event_index)
            if s.station_id == "S1"]
    assert sent[-1] == 120
    assert sim.station_price("S1") == 120


@pytest.mark.parametrize("seed", [0, 3, 99])
def test_station_state_settled_on_p3(seed):
    _scenario(seed)
    state = app.get_station_state("S1")
    assert _field(state, "latest_desired_price") == 120
    assert _field(state, "last_acknowledged_price") == 120
    assert _field(state, "settled") is True
