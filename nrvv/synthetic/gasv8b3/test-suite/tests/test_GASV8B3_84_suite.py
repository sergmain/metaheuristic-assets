import dataclasses
import numbers

import pytest

import app
import nrvv_env

DT = 100
ST = "st-1"
OTHER = "st-2"


def _flatten(obj, path=()):
    out = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, numbers.Number):
        out.append((path, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(_flatten(v, path + (str(k),)))
    elif isinstance(obj, (list, tuple, set)):
        for i, v in enumerate(obj):
            if isinstance(v, (tuple, list)) and len(v) == 2 and isinstance(v[0], str):
                out.extend(_flatten(v[1], path + (v[0],)))
            else:
                out.extend(_flatten(v, path + (str(i),)))
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            out.extend(_flatten(getattr(obj, f.name), path + (f.name,)))
    elif hasattr(obj, "__dict__"):
        for k, v in vars(obj).items():
            out.extend(_flatten(v, path + (str(k),)))
    return out


def _has_period(entries):
    return any(v in (DT, DT + 1, DT + 2, 1) for _, v in entries)


def _has_cost(entries):
    return any(v > 0 for p, v in entries if "cost" in "/".join(p).lower())


def _lagged_scenario():
    sim = nrvv_env.Simulation(seed=1, station_ids=(ST, OTHER), initial_price=5)
    sim.connect(app)
    sim.submit(ST, 10)
    if not sim.in_flight:
        pytest.skip("precondition not reached: send did not go out")
    send = sim.in_flight[0]
    sim.advance_time(DT)
    sim.deliver(send.send_id)
    sim.deliver_ack()
    return sim


def test_lagging_station_reports_stale_period_and_cost():
    sim = _lagged_scenario()
    report = app.get_stale_cost_report()
    flat = _flatten(report)
    mine = [(p, v) for p, v in flat if any(ST == s for s in p)]
    if not mine:
        mine = flat
    assert _has_period(mine)
    assert _has_cost(mine)


def test_total_reports_stale_period_and_cost():
    _lagged_scenario()
    flat = _flatten(app.get_stale_cost_report())
    total = [(p, v) for p, v in flat if "total" in "/".join(p).lower()]
    assert total, "no total in report"
    assert _has_period(total)
    assert _has_cost(total)


def test_station_that_never_lagged_reports_zero():
    _lagged_scenario()
    flat = _flatten(app.get_stale_cost_report())
    other = [(p, v) for p, v in flat if any(OTHER == s for s in p)]
    assert all(v == 0 for _, v in other)
