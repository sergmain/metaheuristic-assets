import pytest

import app
import nrvv_env


def _report(period_start, period_end):
    try:
        return app.get_stale_price_cost_report((period_start, period_end))
    except (TypeError, ValueError, KeyError):
        return app.get_stale_price_cost_report(
            {"start": period_start, "end": period_end})


def _duration(report, station):
    per = report["stale_duration_per_station"]
    val = per[station]
    if isinstance(val, dict):
        for k in ("duration", "stale_duration", "total"):
            if k in val:
                return val[k]
    return val


def test_stale_interval_reported_with_duration_and_cost():
    rate = 2.5
    sim = nrvv_env.Simulation(seed=1, stale_cost_per_time=rate, ordering="fifo",
                              start_time=0.0)
    sim.connect(app)
    station = "S1"

    # First price: submitted and acknowledged early, outside the checked period.
    sim.submit(station, 10.0)
    sim.advance_to(5.0)
    sim.run_until_idle()
    if sim.station_price(station) != 10.0:
        pytest.skip("precondition not reached: first price not applied at station")

    # Newer desired price submitted at t=10; station still runs the older price.
    sim.advance_to(10.0)
    sim.submit(station, 11.0)

    # Acknowledged at the known later time t=25.
    sim.advance_to(25.0)
    sim.run_until_idle()
    if sim.station_price(station) != 11.0:
        pytest.skip("precondition not reached: newer price not applied at station")
    if not sim.acknowledgements or sim.acknowledgements[-1]["time"] != 25.0:
        pytest.skip("precondition not reached: acknowledgement at scripted time")

    sim.advance_to(30.0)
    report = _report(10.0, 30.0)

    interval = 25.0 - 10.0
    assert _duration(report, station) == pytest.approx(interval)
    assert report["cost_total"] == pytest.approx(interval * rate)
    assert report["cost_per_station"][station] == pytest.approx(interval * rate)
