import pytest

import app
import nrvv_env

PERIOD = (0.0, 12.0)
RATE = 2.0
A, B, C = "A", "B", "C"


def approx(x):
    return pytest.approx(x, abs=1e-6)


def build(seed=1):
    sim = nrvv_env.Simulation(seed=seed, cost_per_send=1.0,
                              stale_cost_per_time=RATE, ordering="fifo")
    sim.connect(app)
    sim.submit(A, 10.0)
    sim.advance_to(2.0)
    sim.submit(B, 11.0)
    sim.advance_to(3.0)
    sim.submit(C, 12.0)
    if len(sim.sends) < 3:
        pytest.skip("precondition not reached: sends not issued at submission")
    ords = {}
    for s in sim.sends:
        ords.setdefault(s["station_id"], s["ordinal"])
    if not (ords.get(A, 9) < ords.get(B, 9) < ords.get(C, 9)):
        pytest.skip("precondition not reached: send order A,B,C")
    sim.advance_to(5.0)
    sim.set_arrival_order([ords[A]])
    sim.step_send()
    assert sim.step_ack()
    sim.advance_to(9.0)
    sim.set_arrival_order([ords[B]])
    sim.step_send()
    assert sim.step_ack()
    sim.advance_to(12.0)
    return sim, ords


def flat(x):
    out = []
    if isinstance(x, dict):
        for v in x.values():
            out += flat(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            out += flat(v)
    elif isinstance(x, (int, float)) and not isinstance(x, bool):
        out.append(x)
    return out


def find(rep, *subs):
    for k, v in rep.items():
        lk = str(k).lower()
        if all(s in lk for s in subs):
            return v
    return None


def test_on_demand_totals_per_station_and_duration():
    sim, _ = build()
    rep = app.get_stale_price_cost_report(PERIOD)
    assert rep["cost_total"] == approx(42.0)
    cps = rep["cost_per_station"]
    assert cps[A] == approx(10.0)
    assert cps[B] == approx(14.0)
    assert cps[C] == approx(18.0)
    d = rep["stale_duration_per_station"]
    assert d[A] == approx(5.0)
    assert d[B] == approx(7.0)
    assert d[C] == approx(9.0)


def test_cost_by_cause_adds_up_to_total():
    build()
    rep = app.get_stale_price_cost_report(PERIOD)
    causes = find(rep, "cause")
    assert causes is not None, "report lacks cost by cause"
    assert sum(flat(causes)) == approx(42.0)


def test_interval_count_and_total_duration():
    build()
    rep = app.get_stale_price_cost_report(PERIOD)
    n = find(rep, "interval", "count") or find(rep, "number", "interval") \
        or find(rep, "stale_intervals") or find(rep, "intervals")
    assert n is not None, "report lacks number of stale intervals"
    nums = flat(n)
    assert 3 in nums or 3.0 in nums
    dur = find(rep, "total", "duration") or find(rep, "interval", "duration")
    if dur is not None:
        assert 21.0 in [float(v) for v in flat(dur)]


def test_stations_currently_stale_and_provisional_share():
    build()
    rep = app.get_stale_price_cost_report(PERIOD)
    cur = find(rep, "currently") or find(rep, "stations_stale") or find(rep, "stale_stations")
    assert cur is not None, "report lacks stations currently stale"
    if isinstance(cur, (list, tuple, set, dict)):
        cur = len(cur)
    assert cur == 1
    share = find(rep, "provisional")
    assert share is not None, "report lacks provisional share"
    vals = flat(share)
    assert vals
    assert any(abs(v - 18.0 / 42.0) < 1e-6 or abs(v - 1.0 / 3.0) < 1e-6
               or abs(v - 100.0 / 3.0) < 1e-4 or abs(v - 1800.0 / 42.0) < 1e-4
               for v in vals)


def test_periodic_report_equals_on_demand_for_same_period():
    build()
    on_demand = app.get_stale_price_cost_report(PERIOD)
    fn = None
    for name in ("get_periodic_stale_price_cost_report",
                 "get_periodic_report", "periodic_stale_price_cost_report",
                 "run_periodic_stale_price_cost_report",
                 "produce_periodic_stale_price_cost_report"):
        fn = getattr(app, name, None)
        if callable(fn):
            break
    if fn is None:
        pytest.skip("precondition not reached: no periodic report entry point")
    periodic = fn(PERIOD)
    assert periodic["cost_total"] == approx(on_demand["cost_total"])
    assert periodic["cost_per_station"] == on_demand["cost_per_station"]
    assert periodic["stale_duration_per_station"] == on_demand["stale_duration_per_station"]


def test_earlier_report_reproducible_after_later_events():
    sim, ords = build()
    first = app.get_stale_price_cost_report(PERIOD)
    snap = {k: v for k, v in first.items()}
    sim.advance_to(15.0)
    sim.set_arrival_order([ords[C]])
    sim.step_send()
    assert sim.step_ack()
    sim.advance_to(16.0)
    sim.submit(A, 20.0)
    sim.advance_to(18.0)
    again = app.get_stale_price_cost_report(PERIOD)
    assert again["cost_total"] == approx(snap["cost_total"])
    assert again["cost_per_station"] == snap["cost_per_station"]
    assert again["stale_duration_per_station"] == snap["stale_duration_per_station"]


def test_correction_is_appended_without_changing_earlier_figures():
    sim, ords = build()
    before = app.get_stale_price_cost_report(PERIOD)
    sim.advance_to(14.0)
    sim.submit(B, 99.0)
    sim.advance_to(20.0)
    later = app.get_stale_price_cost_report((0.0, 20.0))
    assert later["cost_total"] > before["cost_total"]
    replay = app.get_stale_price_cost_report(PERIOD)
    assert replay["cost_total"] == approx(before["cost_total"])
    assert replay["cost_per_station"] == before["cost_per_station"]
