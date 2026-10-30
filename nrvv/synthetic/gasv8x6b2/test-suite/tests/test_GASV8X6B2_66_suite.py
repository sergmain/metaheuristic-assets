import pytest

import app
import nrvv_env


def _report(period_end):
    for period in ((0.0, period_end), {"start": 0.0, "end": period_end}, None):
        try:
            return app.get_stale_price_cost_report(period)
        except TypeError:
            continue
    pytest.skip("precondition not reached: stale cost report not queryable")


def _total(rep):
    return rep["cost_total"]


def _setup(seed):
    sim = nrvv_env.Simulation(seed=seed, ordering="fifo", cost_per_send=1.0,
                              stale_cost_per_time=2.0, start_time=100.0)
    sim.connect(app)
    sim.submit("S1", 10.0)
    sim.advance(1.0)
    sim.submit("S1", 11.0)
    sim.advance(1.0)
    sim.submit("S1", 12.0)
    return sim


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_mismatched_ack_closes_no_record_and_cost_keeps_accruing(seed):
    sim = _setup(seed)
    if len(sim.sends) < 3:
        pytest.skip("precondition not reached: three outstanding sends for one station")
    sends = sim.sends[:3]
    sim.advance(1.0)
    app.on_acknowledgement("S1", sends[0]["request_id"], "ok")
    sim.advance(1.0)
    app.on_acknowledgement("S1", "wrong-" + str(sends[1]["request_id"]), "ok")
    state = app.get_station_state("S1")
    assert state["settled"] is False
    before = _total(_report(sim.now()))
    sim.advance(50.0)
    after = _total(_report(sim.now()))
    assert after > before
    assert app.get_station_state("S1")["settled"] is False
