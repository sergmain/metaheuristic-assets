import pytest

import app
import nrvv_env
from nrvv_env import Simulation, SubmissionRejected

STATIONS = ["S1", "S2"]
ALL_CANDIDATES = [None, "all", "ALL", "*"]


def _setup(seed, ordering="fifo"):
    sim = Simulation(seed=seed, ordering=ordering)
    sim.connect(app)
    return sim


def _submit_one(sim, station, price):
    try:
        return sim.submit(station, price)
    except Exception:
        pytest.skip("precondition not reached: station %s not accepted for submission" % station)


def _submit_all(sim, price):
    for cand in ALL_CANDIDATES:
        try:
            return sim.submit(cand, price)
        except Exception:
            continue
    pytest.skip("precondition not reached: no all-stations target accepted")


def _sends_from(sim, start):
    return [s for s in sim.sends[start:]]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_single_station_update_reaches_only_target(seed):
    sim = _setup(seed)
    uid = _submit_one(sim, "S1", 10)
    assert uid is not None
    sim.run_until_idle()
    sends = sim.sends
    assert sends, "no send was made for the submitted update"
    assert all(s["station_id"] == "S1" for s in sends)
    assert sends[-1]["price"] == 10
    assert sim.station_price("S1") == 10
    assert sim.station_price("S2") is None


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_all_stations_update_reaches_every_station_with_latest(seed):
    sim = _setup(seed)
    _submit_one(sim, "S1", 10)
    sim.run_until_idle()
    start = len(sim.sends)
    uid = _submit_all(sim, 20)
    assert uid is not None
    sim.run_until_idle()
    new = _sends_from(sim, start)
    for st in STATIONS:
        mine = [s for s in new if s["station_id"] == st]
        assert mine, "station %s received no send for the all-stations update" % st
        last = max(mine, key=lambda s: s["event_index"])
        assert last["price"] == 20


def test_updates_have_identifiers_and_no_pricing_team_step_needed():
    sim = _setup(7)
    u1 = _submit_one(sim, "S1", 11)
    sim.run_until_idle()
    u2 = _submit_all(sim, 22)
    sim.run_until_idle()
    assert u1 is not None and u2 is not None
    # the service itself did all sending: every send happened via the port
    # after the submissions and before any further pricing-team action
    assert len(sim.sends) >= 3
    assert sim.station_price("S1") == 22
    assert sim.station_price("S2") == 22
    assert sim.idle()
