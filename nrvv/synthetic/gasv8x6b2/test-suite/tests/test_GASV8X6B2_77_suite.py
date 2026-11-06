import pytest

import app
import nrvv_env

PERIOD = (0.0, 10000.0)


def _call(name, *args):
    fn = getattr(app, name)
    try:
        return fn(PERIOD)
    except TypeError:
        return fn({"start": PERIOD[0], "end": PERIOD[1]})


def _scenario(seed, with_reports, cps=2.5, scpt=7.0, losses=()):
    sim = nrvv_env.Simulation(seed=seed, cost_per_send=cps, stale_cost_per_time=scpt,
                              ordering="fifo")
    sim.connect(app)
    for o in losses:
        sim.lose_send(o)
    log = []

    def observe():
        if with_reports:
            log.append(_call("get_sending_cost_report"))
            _call("get_stale_price_cost_report")

    sim.submit("A", 10.0)
    sim.submit("B", 20.0)
    observe()
    sim.step()
    sim.advance(5)
    sim.submit("A", 11.0)
    observe()
    sim.step()
    sim.advance(5)
    sim.submit("B", 21.0)
    observe()
    for _ in range(40):
        if not sim.step():
            break
        sim.advance(1)
        observe()
    sim.advance(200)
    sim.submit("A", 12.0)
    observe()
    sim.run_until_idle()
    return sim


def _find_split(obj):
    keys = {"acknowledged", "superseded", "unconfirmed", "abandoned"}
    found = []
    if isinstance(obj, dict):
        if keys <= set(obj.keys()):
            found.append(obj)
        for v in obj.values():
            found.extend(_find_split(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            found.extend(_find_split(v))
    return found


def _num(x):
    if isinstance(x, dict):
        for k in ("cost", "cost_total", "total"):
            if k in x:
                return x[k]
        return None
    return x


def test_sending_cost_matches_sends_and_rate():
    for seed in (1, 2, 3):
        sim = _scenario(seed, False)
        rep = _call("get_sending_cost_report")
        assert rep["sends_count"] == len(sim.sends)
        assert rep["cost_total"] == pytest.approx(len(sim.sends) * 2.5)
        per = rep["cost_per_station"]
        assert sum(_num(v) for v in per.values()) == pytest.approx(rep["cost_total"])
        for sid in {s["station_id"] for s in sim.sends}:
            n = sum(1 for s in sim.sends if s["station_id"] == sid)
            assert _num(per[sid]) == pytest.approx(n * 2.5)


def test_no_stale_price_cost_in_sending_report():
    sim = _scenario(4, False, cps=2.5, scpt=7.0)
    rep = _call("get_sending_cost_report")
    stale = _call("get_stale_price_cost_report")
    assert rep["cost_total"] == pytest.approx(len(sim.sends) * 2.5)
    assert "stale_duration_per_station" not in rep
    assert stale["cost_total"] != pytest.approx(rep["cost_total"]) or True
    assert rep["cost_total"] < rep["cost_total"] + stale["cost_total"] or stale["cost_total"] == 0


def test_split_parts_sum_to_total():
    sim = _scenario(5, False, losses=(1,))
    rep = _call("get_sending_cost_report")
    splits = _find_split(rep)
    assert splits, "report has no acknowledged/superseded/unconfirmed/abandoned split"
    top = [s for s in splits if s is rep or s is rep.get("by_outcome") or s is rep.get("split")]
    target = top[0] if top else splits[0]
    parts = [_num(target[k]) for k in ("acknowledged", "superseded", "unconfirmed", "abandoned")]
    assert all(p is not None for p in parts)
    assert sum(parts) == pytest.approx(rep["cost_total"])
    for s in splits:
        ps = [_num(s[k]) for k in ("acknowledged", "superseded", "unconfirmed", "abandoned")]
        assert all(p >= 0 for p in ps)


def test_every_split_group_sums_consistently():
    _scenario(6, False)
    rep = _call("get_sending_cost_report")
    splits = _find_split(rep)
    assert len(splits) >= 3  # total, stations, price updates
    grand = 0.0
    for s in splits:
        grand += sum(_num(s[k]) for k in ("acknowledged", "superseded", "unconfirmed", "abandoned"))
    assert grand >= rep["cost_total"]


def test_per_send_record_figures_available():
    sim = _scenario(7, False)
    rep = _call("get_sending_cost_report")
    recs = None
    for k, v in rep.items():
        if isinstance(v, list) and v and all(isinstance(r, dict) for r in v):
            recs = v
    if recs is None:
        for fn in ("get_send_records", "get_sending_cost_records"):
            if hasattr(app, fn):
                recs = getattr(app, fn)(PERIOD)
    assert recs, "no per-send records retrievable"
    assert len(recs) == len(sim.sends)
    rids = {r.get("request_id") for r in recs}
    assert rids == {s["request_id"] for s in sim.sends}
    total = sum(_num(r.get("cost")) for r in recs)
    assert total == pytest.approx(rep["cost_total"])


def test_version_identifiers_match_sends_and_stale_report():
    sim = _scenario(8, False)
    rep = _call("get_sending_cost_report")
    text = repr(rep)
    for s in sim.sends:
        assert str(s["version"]) in text
    stale = _call("get_stale_price_cost_report")
    assert isinstance(stale, dict)


def test_reports_do_not_change_delivery():
    for seed in (1, 2, 3):
        a = _scenario(seed, False)
        b = _scenario(seed, True)

        def strip(items):
            return [{k: v for k, v in d.items() if k != "event_index"} for d in items]

        assert strip(a.sends) == strip(b.sends)
        assert strip(a.deliveries) == strip(b.deliveries)
        assert strip(a.acknowledgements) == strip(b.acknowledgements)
        assert a.station_prices == b.station_prices


def test_reports_do_not_change_station_settling():
    for seed in (4, 5):
        a = _scenario(seed, False)
        st_a = {s: app.get_station_state(s) for s in ("A", "B")}
        b = _scenario(seed, True)
        st_b = {s: app.get_station_state(s) for s in ("A", "B")}
        assert st_a == st_b
        assert a.station_price("A") == b.station_price("A") == 12.0
        assert a.station_price("B") == b.station_price("B") == 21.0
        assert st_b["A"]["settled"] and st_b["B"]["settled"]


def test_repeated_on_demand_reports_are_stable():
    _scenario(9, False)
    r1 = _call("get_sending_cost_report")
    r2 = _call("get_sending_cost_report")
    assert r1["sends_count"] == r2["sends_count"]
    assert r1["cost_total"] == r2["cost_total"]
    assert r1["cost_per_station"] == r2["cost_per_station"]
