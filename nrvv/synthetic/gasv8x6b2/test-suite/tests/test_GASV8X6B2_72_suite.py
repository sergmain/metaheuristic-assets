import pytest

import app
import nrvv_env


def _station_sends(sim, sid):
    return [s for s in sim.sends if s["station_id"] == sid]


def _setup(seed, sid):
    sim = nrvv_env.Simulation(seed=seed, ordering="fifo")
    sim.connect(app)
    sim.submit(sid, 10.0)
    first = _station_sends(sim, sid)
    if not first:
        pytest.skip("precondition not reached: no send of version 1 issued")
    r1 = first[0]
    sim.submit(sid, 12.0)
    return sim, r1


def _ack_r1(sim, r1):
    assert sim.step_send()
    assert sim.step_ack()
    ack = sim.acknowledgements[-1]
    assert ack["request_id"] == r1["request_id"]
    return ack


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_ack_of_superseded_version_leaves_station_not_settled(seed):
    sid = "st-a-%d" % seed
    sim, r1 = _setup(seed, sid)
    _ack_r1(sim, r1)
    st = app.get_station_state(sid)
    assert st["settled"] is False
    assert st["latest_desired_price"] == 12.0
    assert st["latest_version"] > r1["version"]


def test_only_ack_of_latest_version_settles_station():
    sid = "st-b"
    sim, r1 = _setup(7, sid)
    _ack_r1(sim, r1)
    assert app.get_station_state(sid)["settled"] is False
    later = [s for s in _station_sends(sim, sid) if s["version"] > r1["version"]]
    if not later:
        pytest.skip("precondition not reached: no send of the newer version issued")
    r2 = later[-1]
    assert r2["price"] == 12.0
    assert r2["request_id"] != r1["request_id"]
    assert sim.step_send()
    assert app.get_station_state(sid)["settled"] is False
    assert sim.step_ack()
    assert sim.acknowledgements[-1]["request_id"] == r2["request_id"]
    st = app.get_station_state(sid)
    assert st["settled"] is True
    assert st["last_acknowledged_price"] == 12.0
