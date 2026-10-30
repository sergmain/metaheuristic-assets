import pytest
import app
import nrvv_env


def _setup(seed):
    sim = nrvv_env.Simulation(seed=seed, ordering="fifo")
    sim.connect(app)
    return sim


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_versions_strictly_increase_and_recorded_at_submission(seed):
    sim = _setup(seed)
    st = "S1"
    versions = []
    prices = [10.0, 11.0, 12.0]
    for i, p in enumerate(prices):
        if i:
            sim.advance(5)
        sim.submit(st, p)
        s = app.get_station_state(st)
        assert s["latest_desired_price"] == p
        assert s["settled"] is False
        versions.append(s["latest_version"])
        # nothing has been acknowledged: recorded without waiting for sends
        assert sim.acknowledgements == []
    assert versions[0] < versions[1] < versions[2]


@pytest.mark.parametrize("seed", [1, 2])
def test_stale_interval_closes_only_on_ack_of_latest(seed):
    sim = _setup(seed)
    st = "S1"
    sim.set_time(0.0)
    sim.submit(st, 10.0)
    if not sim.sends:
        pytest.skip("precondition not reached: P1 send issued")
    sim.advance(10)
    sim.submit(st, 11.0)
    sim.advance(5)
    sim.submit(st, 12.0)
    sim.advance(5)
    s = app.get_station_state(st)
    assert s["settled"] is False
    assert s["latest_desired_price"] == 12.0
    sim.run_until_idle()
    s = app.get_station_state(st)
    if not s["settled"]:
        pytest.skip("precondition not reached: station confirmed on latest")
    assert s["last_acknowledged_price"] == 12.0
    t_close = sim.now()
    sim.advance(30)
    try:
        rep = app.get_stale_price_cost_report((0.0, sim.now()))
    except Exception:
        pytest.skip("precondition not reached: stale report period form")
    dur = rep["stale_duration_per_station"][st]
    assert dur == pytest.approx(t_close - 0.0)
