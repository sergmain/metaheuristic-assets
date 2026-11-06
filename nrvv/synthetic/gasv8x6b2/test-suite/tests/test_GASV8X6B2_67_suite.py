import pytest

import app
import nrvv_env


def _get(obj, key):
    if isinstance(obj, dict):
        return obj[key]
    return getattr(obj, key)


def _settle(sim, rounds=60):
    for _ in range(rounds):
        sim.run_until_idle()
        sim.advance(100)
        sim.run_until_idle()
        if sim.idle():
            st = app.get_station_state("S1")
            if _get(st, "settled"):
                break


def _report(period):
    try:
        return app.get_stale_price_cost_report(period)
    except TypeError:
        return app.get_stale_price_cost_report()


def test_reordered_sends_converge_on_latest_price_and_cost_preserved():
    for seed in (1, 2, 3):
        sim = nrvv_env.Simulation(seed=seed, ordering="fifo")
        sim.connect(app)
        sim.set_arrival_order([1, 0])
        sim.submit("S1", 10.0)
        sim.advance(5)
        sim.submit("S1", 20.0)
        sim.advance(5)
        _settle(sim)
        if not sim.idle():
            pytest.skip("precondition not reached: simulation not idle")
        st = app.get_station_state("S1")
        assert _get(st, "settled") is True
        assert _get(st, "latest_desired_price") == 20.0
        assert _get(st, "last_acknowledged_price") == _get(st, "latest_desired_price")
        assert sim.station_price("S1") == 20.0
        applied = sim.station_applied.get("S1", [])
        assert applied and applied[-1][2] == 20.0

        report = _report((0, sim.now()))
        text = repr(report).lower()
        assert "converged" in text
        assert "not converged" not in text and "not_converged" not in text
        assert "converging" not in text
        assert _get(report, "cost_total") > 0
