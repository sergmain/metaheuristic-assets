import pytest
import app
from nrvv_env import Simulation

STATION = "S1"
PRICES = [1.10, 1.20, 1.30]


def _get(state, *names):
    for n in names:
        if isinstance(state, dict) and n in state:
            return state[n]
        if hasattr(state, n):
            return getattr(state, n)
    return None


def _drive(seed, ordering):
    sim = Simulation(seed=seed, ordering=ordering, start_time=0.0)
    sim.connect(app)
    for i, p in enumerate(PRICES):
        sim.advance_to(float(i + 1))
        sim.submit(STATION, p)
    max_seen = 0
    steps = 0
    while steps < 500 and sim.step():
        steps += 1
        if not sim.acknowledgements:
            continue
        last = sim.acknowledgements[-1]
        if last.get("checked"):
            continue
        last["checked"] = True
        send = sim.sends[last["ordinal"]]
        ver = send["version"]
        if ver < max_seen and ver < len(PRICES):
            return sim, send, last
        max_seen = max(max_seen, ver)
        sim.advance(1.0)
    return sim, None, None


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_older_send_ack_regresses_confirmed_version(seed):
    found = None
    for ordering in ("random", "fifo"):
        sim, send, ack = _drive(seed, ordering)
        if send is not None:
            found = (sim, send, ack)
            break
    if found is None:
        pytest.skip("precondition not reached: ack for older send after newer confirmed")
    sim, send, ack = found
    state = app.get_station_state(STATION)
    assert _get(state, "last_acknowledged_price", "last_confirmed_price") == send["price"]
    assert _get(state, "settled") is False
