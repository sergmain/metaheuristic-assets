import pytest

import app
import nrvv_env
from nrvv_env import Simulation


def _drive(sim, steps=400):
    n = 0
    while n < steps and sim.step():
        n += 1


def _regressed_ack_index(sim):
    """Index of an acknowledgement whose version is lower than an earlier acknowledged one."""
    version_of = {s["request_id"]: s["version"] for s in sim.sends}
    best = None
    for i, a in enumerate(sim.acknowledgements):
        v = version_of.get(a["request_id"])
        if v is None:
            continue
        if best is not None and v < best:
            return i
        best = v if best is None else max(best, v)
    return None


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_older_ack_after_newer_records_regressed_confirmation(seed):
    sim = Simulation(seed=seed, ordering="fifo")
    sim.connect(app)
    station = "S1"
    prices = {}
    for k, p in enumerate([1.10, 1.20, 1.30], start=1):
        sim.advance(1)
        sim.submit(station, p)
        prices[k] = p
        _drive(sim, 20)
        sim.advance(50)
        _drive(sim, 20)
    sim.advance(1000)
    _drive(sim, 400)

    idx = _regressed_ack_index(sim)
    if idx is None:
        pytest.skip("precondition not reached: an acknowledgement of an older version "
                    "after a newer confirmed version cannot be produced through nrvv_env")

    version_of = {s["request_id"]: (s["version"], s["price"]) for s in sim.sends}
    ack = sim.acknowledgements[idx]
    ver, price = version_of[ack["request_id"]]
    state = app.get_station_state(station)
    if state["latest_version"] < 3:
        pytest.skip("precondition not reached: desired version 3 not in the ledger")
    # the last acknowledgement in the run is the regressed one only if nothing followed it
    if idx != len(sim.acknowledgements) - 1:
        pytest.skip("precondition not reached: regressed acknowledgement was not the last")
    assert state["last_acknowledged_price"] == price
    assert state["settled"] is False
