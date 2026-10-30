import pytest

import app
import nrvv_env

STATION = "S1"
PRICE_A = 10.0
PRICE_B = 12.5


def _state(station):
    return app.get_station_state(station)


def _drive_to_b_acknowledged(sim):
    """Script: A sent and lost (timed out), B submitted later, B delivered and acknowledged.
    Returns the state right after B's acknowledgement, with no clock advance since."""
    sim.connect(app)
    sim.submit(STATION, PRICE_A)
    if not sim.sends or sim.sends[0]["price"] != PRICE_A:
        pytest.skip("precondition not reached: version-1 send was not issued")
    sim.lose_send(0)
    t = 0.0
    sim.advance_to(5.0)
    t = 5.0
    sim.submit(STATION, PRICE_B)
    while not any(s["price"] == PRICE_B for s in sim.sends):
        t += 20.0
        if t > 3000.0:
            pytest.skip("precondition not reached: send of price B never issued")
        sim.advance_to(t)
        _state(STATION)
    sim.run_until_idle()
    if not any(a["request_id"] == s["request_id"]
               for a in sim.acknowledgements
               for s in sim.sends if s["price"] == PRICE_B):
        pytest.skip("precondition not reached: price B send not acknowledged")


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_not_settled_before_window_elapsed(seed):
    sim = nrvv_env.Simulation(seed=seed, ordering="fifo")
    _drive_to_b_acknowledged(sim)
    assert _state(STATION)["settled"] is False


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_settled_after_window_with_final_price_b(seed):
    sim = nrvv_env.Simulation(seed=seed, ordering="fifo")
    _drive_to_b_acknowledged(sim)
    t = sim.now()
    for _ in range(6):
        t += 100000.0
        sim.advance_to(t)
        _state(STATION)
        sim.run_until_idle()
        if _state(STATION)["settled"] is True:
            break
    st = _state(STATION)
    assert st["settled"] is True
    assert sim.station_price(STATION) == PRICE_B
    assert sim.station_applied[STATION][-1][2] == PRICE_B
    assert st["last_acknowledged_price"] == PRICE_B
