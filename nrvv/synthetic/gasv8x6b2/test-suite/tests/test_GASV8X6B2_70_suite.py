import importlib

import pytest

import app as _app_module
import nrvv_env


def _fresh(seed, ordering="fifo", **kw):
    app = importlib.reload(_app_module)
    sim = nrvv_env.Simulation(seed=seed, ordering=ordering, **kw)
    sim.connect(app)
    return app, sim


def _settle(app, sim, station, rounds=40):
    """Drive transport, advancing the clock between rounds so retries can fire."""
    for i in range(rounds):
        sim.run_until_idle()
        if app.get_station_state(station)["settled"] and sim.idle():
            return True
        sim.advance(min(2 ** i, 64))
        sim.run_until_idle()
    return app.get_station_state(station)["settled"]


def _latest_before(sim, station, event_index):
    best = None
    for s in sim.submissions:
        if s["station_id"] == station and s["event_index"] < event_index:
            best = s
    return best


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_superseded_price_never_resent_after_newer_submitted(seed):
    app, sim = _fresh(seed, ordering="random")
    sim.submit("S1", 100)
    if not sim.sends or sim.sends[0]["price"] != 100:
        pytest.skip("precondition not reached: first send of P1 not issued on submit")
    sim.submit("S1", 200)
    p2_event = sim.submissions[-1]["event_index"]
    assert _settle(app, sim, "S1")
    for s in sim.sends:
        if s["event_index"] > p2_event:
            assert s["price"] == 200
    assert sim.station_applied["S1"][-1][2] == 200
    assert sum(1 for s in sim.sends if s["price"] == 100) == 1
    assert any(s["price"] == 200 for s in sim.sends)


@pytest.mark.parametrize("seed", [4, 5, 6])
def test_each_send_carries_desired_price_at_send_time(seed):
    app, sim = _fresh(seed, ordering="random")
    sim.submit("S1", 10)
    sim.submit("S1", 20)
    sim.step()
    sim.submit("S1", 30)
    sim.step()
    sim.submit("S1", 40)
    assert _settle(app, sim, "S1")
    assert sim.sends
    for s in sim.sends:
        latest = _latest_before(sim, "S1", s["event_index"])
        assert latest is not None
        assert s["price"] == latest["price"]
    assert sim.sends[-1]["price"] == 40


@pytest.mark.parametrize("seed", [7, 8])
def test_no_sends_after_convergence(seed):
    app, sim = _fresh(seed)
    sim.submit("S1", 5)
    sim.submit("S1", 6)
    assert _settle(app, sim, "S1")
    st = app.get_station_state("S1")
    assert st["settled"] is True
    assert st["last_acknowledged_price"] == 6
    n = len(sim.sends)
    for _ in range(10):
        sim.advance(100)
        sim.run_until_idle()
    assert len(sim.sends) == n
    assert sim.station_price("S1") == 6


@pytest.mark.parametrize("seed", [9, 10])
def test_lost_send_is_retried_with_latest_price(seed):
    app, sim = _fresh(seed)
    sim.lose_send(0)
    sim.submit("S1", 100)
    if not sim.sends:
        pytest.skip("precondition not reached: no first send issued on submit")
    sim.submit("S1", 200)
    p2_event = sim.submissions[-1]["event_index"]
    assert _settle(app, sim, "S1", rounds=60)
    assert sim.losses
    assert sim.station_price("S1") == 200
    for s in sim.sends:
        if s["event_index"] > p2_event:
            assert s["price"] == 200
    assert app.get_station_state("S1")["last_acknowledged_price"] == 200


def test_repeated_losses_keep_retrying_until_confirmed():
    app, sim = _fresh(11)
    for o in range(3):
        sim.lose_send(o)
    sim.submit("S1", 50)
    assert _settle(app, sim, "S1", rounds=80)
    assert len(sim.losses) == 3
    assert len(sim.sends) >= 4
    assert all(s["price"] == 50 for s in sim.sends)
    assert sim.station_price("S1") == 50
    n = len(sim.sends)
    sim.advance(1000)
    sim.run_until_idle()
    assert len(sim.sends) == n


def test_stations_converge_independently_on_latest():
    app, sim = _fresh(12, ordering="random")
    sim.submit("A", 1)
    sim.submit("B", 2)
    sim.submit("A", 3)
    sim.submit("B", 4)
    assert _settle(app, sim, "A")
    assert _settle(app, sim, "B")
    assert sim.station_price("A") == 3
    assert sim.station_price("B") == 4
    for s in sim.sends:
        latest = _latest_before(sim, s["station_id"], s["event_index"])
        assert s["price"] == latest["price"]
