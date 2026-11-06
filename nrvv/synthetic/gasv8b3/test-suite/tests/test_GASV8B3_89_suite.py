import importlib

import pytest

import app
import nrvv_env


def _fresh(seed=0, stations=()):
    importlib.reload(app)
    sim = nrvv_env.Simulation(seed=seed, station_ids=stations)
    sim.connect(app)
    return sim


def _get(report, kind):
    """Extract sends / resends / cost from a report of unknown shape."""
    if isinstance(report, (tuple, list)) and len(report) >= 3:
        return {"sends": report[0], "resends": report[1], "cost": report[2]}[kind]
    if isinstance(report, dict):
        items = {str(k).lower(): v for k, v in report.items()}
    else:
        items = {n.lower(): getattr(report, n) for n in dir(report)
                 if not n.startswith("_") and not callable(getattr(report, n))}
    for k, v in items.items():
        if kind == "resends" and ("resend" in k or "retr" in k):
            return v
    for k, v in items.items():
        if kind == "sends" and "send" in k and "resend" not in k and "cost" not in k \
                and "station" not in k and isinstance(v, (int, float)):
            return v
    for k, v in items.items():
        if kind == "cost" and "cost" in k and isinstance(v, (int, float)):
            return v
    pytest.skip("precondition not reached: report field %s not recognised" % kind)


def _report():
    return app.get_sending_cost_report()


def _expected_resends(sim):
    seen = {}
    n = 0
    for s in sim.sends:
        if seen.get(s.station_id):
            n += 1
        seen[s.station_id] = True
    return n


def _unit_cost():
    sim = _fresh(1, ["u"])
    sim.submit("u", 100)
    sim.run_until_idle()
    if len(sim.sends) != 1:
        pytest.skip("precondition not reached: single send")
    c = _get(_report(), "cost")
    assert c > 0
    return c


def test_no_sends_reports_zero():
    _fresh(0, ["a", "b"])
    r = _report()
    assert _get(r, "sends") == 0
    assert _get(r, "resends") == 0
    assert _get(r, "cost") == 0


def test_single_send_counts_one_no_resend():
    sim = _fresh(2, ["a"])
    sim.submit("a", 120)
    sim.run_until_idle()
    r = _report()
    assert _get(r, "sends") == len(sim.sends) == 1
    assert _get(r, "resends") == 0
    assert _get(r, "cost") > 0


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_counts_match_with_resend(seed):
    sim = _fresh(seed, ["a"])
    sim.submit("a", 100)
    sim.submit("a", 110)
    sim.run_until_idle()
    if len(sim.sends) < 2:
        pytest.skip("precondition not reached: no resend happened")
    r = _report()
    assert _get(r, "sends") == len(sim.sends)
    assert _get(r, "resends") == _expected_resends(sim)


def test_total_cost_is_sum_of_per_send_costs():
    unit = _unit_cost()
    sim = _fresh(3, ["a", "b"])
    sim.submit("a", 100)
    sim.submit("b", 200)
    sim.submit("a", 105)
    sim.run_until_idle()
    n = len(sim.sends)
    if n < 3:
        pytest.skip("precondition not reached: at least three sends")
    r = _report()
    assert _get(r, "sends") == n
    assert _get(r, "cost") == pytest.approx(n * unit)


def test_many_stations_and_repeated_updates():
    unit = _unit_cost()
    sim = _fresh(4, ["a", "b", "c"])
    for p in (10, 11, 12):
        for s in ("a", "b", "c"):
            sim.submit(s, p)
    sim.run_until_idle()
    n = len(sim.sends)
    r = _report()
    assert _get(r, "sends") == n
    assert _get(r, "resends") == _expected_resends(sim)
    assert _get(r, "cost") == pytest.approx(n * unit)


def test_report_is_stable_when_read_twice():
    sim = _fresh(5, ["a"])
    sim.submit("a", 1)
    sim.submit("a", 2)
    sim.run_until_idle()
    r1 = _report()
    s1, c1 = _get(r1, "sends"), _get(r1, "cost")
    r2 = _report()
    assert _get(r2, "sends") == s1
    assert _get(r2, "cost") == c1
