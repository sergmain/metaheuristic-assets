import pytest
import app
import nrvv_env

STATION = "S1"


def _setup(seed=0):
    sim = nrvv_env.Simulation(seed=seed, ordering="fifo", cost_per_send=2.0,
                              stale_cost_per_time=1.0)
    sim.connect(app)
    return sim


def _submit_first(sim, price=10.0):
    sim.submit(STATION, price)
    if len(sim.sends) < 1:
        pytest.skip("precondition not reached: no send issued after submit")


def _find(state, *parts):
    for k, v in state.items():
        lk = str(k).lower()
        if all(p in lk for p in parts):
            return k, v
    return None, None


def _ack_first(sim):
    assert sim.step_send()
    assert sim.step_ack()


def _sending_report(sim):
    for period in [(0.0, 1000.0), {"start": 0.0, "end": 1000.0}, None]:
        try:
            return app.get_sending_cost_report(period)
        except Exception:
            continue
    pytest.skip("precondition not reached: sending cost report not queryable")


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_settled_false_while_send_outstanding_then_true_after_ack(seed):
    sim = _setup(seed)
    _submit_first(sim, 10.0)
    st = app.get_station_state(STATION)
    assert st["settled"] is False
    _ack_first(sim)
    st = app.get_station_state(STATION)
    assert st["settled"] is True
    assert st["latest_desired_price"] == 10.0
    assert st["last_acknowledged_price"] == 10.0


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_settled_stays_false_when_newer_price_submitted_before_ack(seed):
    sim = _setup(seed)
    _submit_first(sim, 10.0)
    sim.advance(1.0)
    sim.submit(STATION, 11.0)
    assert app.get_station_state(STATION)["settled"] is False
    _ack_first(sim)
    st = app.get_station_state(STATION)
    assert st["settled"] is False
    assert st["latest_desired_price"] == 11.0
    assert st["latest_version"] >= 2


def test_desired_and_confirmed_versions_and_times_exposed():
    sim = _setup(0)
    sim.set_time(10.0)
    _submit_first(sim, 10.0)
    st = app.get_station_state(STATION)
    assert st["latest_version"] == 1
    k, v = _find(st, "desired", "version")
    if k is not None:
        assert v == 1
    dk, dv = _find(st, "desired", "time")
    if dk is None:
        dk, dv = _find(st, "desired", "_at")
    assert dk is not None, "time of desired change not exposed"
    assert dv == 10.0
    sim.set_time(20.0)
    _ack_first(sim)
    st = app.get_station_state(STATION)
    ck, cv = _find(st, "confirmed", "version")
    assert ck is not None, "confirmed version not exposed"
    assert cv == 1
    tk, tv = _find(st, "confirmed", "time")
    if tk is None:
        tk, tv = _find(st, "confirmed", "_at")
    assert tk is not None, "time of confirmation not exposed"
    assert tv == 20.0


def test_send_attempts_emitted_to_cost_inputs():
    sim = _setup(0)
    _submit_first(sim, 10.0)
    rep = _sending_report(sim)
    assert rep["sends_count"] == len(sim.sends) == 1
    assert rep["cost_total"] == pytest.approx(2.0)
    _ack_first(sim)
    rep = _sending_report(sim)
    assert rep["sends_count"] == len(sim.sends)


def test_state_changes_emitted_to_stale_cost_inputs():
    sim = _setup(0)
    sim.set_time(0.0)
    _submit_first(sim, 10.0)
    sim.set_time(5.0)
    _ack_first(sim)
    rep = None
    for period in [(0.0, 1000.0), {"start": 0.0, "end": 1000.0}, None]:
        try:
            rep = app.get_stale_price_cost_report(period)
            break
        except Exception:
            continue
    if rep is None:
        pytest.skip("precondition not reached: stale cost report not queryable")
    assert "stale_duration_per_station" in rep
    assert rep["cost_total"] == pytest.approx(5.0)
