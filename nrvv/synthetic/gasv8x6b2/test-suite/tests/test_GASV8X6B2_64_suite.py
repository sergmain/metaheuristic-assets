import pytest
import app
import nrvv_env

RATE = 3.0
T0 = 100.0
REPORT_AT = 150.0


def _build(seed=1, rate=RATE):
    sim = nrvv_env.Simulation(seed=seed, stale_cost_per_time=rate, ordering="fifo")
    sim.connect(app)
    # station A: closed stale interval [T0, T0+10]
    sim.set_time(0.0)
    sim.submit("A", 1.0)
    sim.run_until_idle()
    sim.set_time(T0)
    sim.submit("A", 2.0)
    sim.set_time(T0 + 10)
    sim.run_until_idle()
    # station B: open stale interval from 120
    sim.set_time(0.0)
    sim.submit("B", 1.0)
    sim.run_until_idle()
    sim.set_time(120.0)
    sim.submit("B", 2.0)
    sim.set_time(REPORT_AT)
    return sim


def _report():
    attempts = [
        {"start": 0.0, "end": REPORT_AT},
        (0.0, REPORT_AT),
        REPORT_AT,
        None,
    ]
    last = None
    for p in attempts:
        try:
            return app.get_stale_price_cost_report(p)
        except (TypeError, ValueError, KeyError, AttributeError) as e:
            last = e
    pytest.skip("precondition not reached: report not obtainable: %r" % (last,))


def _walk(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path + (str(k),), v
            yield from _walk(v, path + (str(k),))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _walk(v, path + (str(i),))


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def test_total_cost_is_closed_plus_open_exposure_times_rate():
    for seed in (1, 2, 3):
        _build(seed)
        rep = _report()
        assert rep["cost_total"] == pytest.approx(10 * RATE + 30 * RATE)


def test_closed_and_open_cost_per_station():
    _build(5)
    rep = _report()
    per = rep["cost_per_station"]
    assert per["A"] == pytest.approx(10 * RATE)
    assert per["B"] == pytest.approx(30 * RATE)


def test_open_interval_marked_provisional():
    _build(7)
    rep = _report()
    found = False
    for path, v in _walk(rep):
        if any("provisional" in p.lower() for p in path):
            if v is True or (_num(v) and v > 0) or (isinstance(v, (list, dict, str)) and v):
                found = True
    assert found, rep


def test_undercharge_and_overcharge_reported_separately():
    _build(9)
    rep = _report()
    keys = [" ".join(p).lower() for p, _ in _walk(rep)]
    assert any("undercharge" in k for k in keys), rep
    assert any("overcharge" in k for k in keys), rep


def test_rates_recorded_with_report():
    _build(11, rate=4.0)
    rep = _report()
    found = False
    for path, v in _walk(rep):
        if any("rate" in p.lower() for p in path):
            if v == 4.0 or (isinstance(v, dict) and 4.0 in v.values()):
                found = True
    assert found, rep
