import pytest
import app
import nrvv_env


STATIONS = ("S1", "S2")


def _scenario(seed, stop_before_last_resolve=True, report_hook=None):
    """S1 gets two prices (first send resolves, follow-up stays in flight); S2 one price."""
    sim = nrvv_env.Simulation(seed=seed, station_ids=STATIONS, initial_price=90)
    sim.connect(app)
    sim.submit("S1", 100)
    sim.submit("S2", 50)
    sim.submit("S1", 110)  # arrives while first S1 send is in flight
    # resolve S2 and first S1 send completely
    guard = 0
    while guard < 50:
        guard += 1
        if sim.pending_acks:
            sim.deliver_ack()
            continue
        fl = sim.in_flight
        if len(fl) <= 1 and any(r.station_id == "S1" and r.price == 110 for r in fl):
            break
        if not fl:
            break
        # deliver anything except the follow-up S1 send
        cand = [r for r in fl if not (r.station_id == "S1" and r.price == 110)]
        if not cand:
            break
        sim.deliver(cand[0].send_id)
    return sim


def _call_report(sim, scope):
    names = ("get_cost_report", "get_sending_cost_report", "cost_report", "get_cost_reporting")
    t_end = sim.now + 1000
    kwargs_options = {
        "station": [{"station_id": "S1"}, {"station": "S1"}],
        "batch": [{"batch": "S1"}, {"batch_id": "S1"}, {"station_id": "S1", "batch": None}],
        "window": [{"start": 0, "end": t_end}, {"window": (0, t_end)},
                   {"time_window": (0, t_end)}, {"from_time": 0, "to_time": t_end}],
    }[scope]
    for n in names:
        fn = getattr(app, n, None)
        if not callable(fn):
            continue
        for kw in kwargs_options:
            try:
                return fn(**kw)
            except TypeError:
                continue
    pytest.skip("precondition not reached: cost reporting interface for %s not callable" % scope)


def _find(obj, *subs):
    """Find first value whose key contains all of subs (case-insensitive), recursive."""
    if isinstance(obj, dict):
        items = list(obj.items())
    elif hasattr(obj, "__dict__"):
        items = list(vars(obj).items())
    else:
        return None
    for k, v in items:
        if all(s in str(k).lower() for s in subs):
            return v
    for _, v in items:
        r = _find(v, *subs)
        if r is not None:
            return r
    return None


def _finish(sim):
    sim.run_until_idle()


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_station_report_provisional_then_final(seed):
    sim = _scenario(seed)
    if not any(r.station_id == "S1" for r in sim.in_flight):
        pytest.skip("precondition not reached: last send outstanding")
    rep = _call_report(sim, "station")
    prov = _find(rep, "provisional")
    assert prov is not None and bool(prov) is True
    _finish(sim)
    rep2 = _call_report(sim, "station")
    prov2 = _find(rep2, "provisional")
    assert prov2 is not None and bool(prov2) is False


def test_batch_report_provisional_then_final():
    sim = _scenario(5)
    if not sim.in_flight:
        pytest.skip("precondition not reached: last send outstanding")
    rep = _call_report(sim, "batch")
    assert bool(_find(rep, "provisional")) is True
    _finish(sim)
    rep2 = _call_report(sim, "batch")
    prov2 = _find(rep2, "provisional")
    assert prov2 is not None and bool(prov2) is False


def test_window_report_provisional_then_final():
    sim = _scenario(7)
    if not sim.in_flight:
        pytest.skip("precondition not reached: last send outstanding")
    rep = _call_report(sim, "window")
    assert bool(_find(rep, "provisional")) is True
    _finish(sim)
    rep2 = _call_report(sim, "window")
    prov2 = _find(rep2, "provisional")
    assert prov2 is not None and bool(prov2) is False


@pytest.mark.parametrize("scope", ["station", "batch", "window"])
def test_report_states_required_figures_and_totals(scope):
    sim = _scenario(11)
    _finish(sim)
    rep = _call_report(sim, scope)
    assert _find(rep, "send") is not None
    assert _find(rep, "retr") is not None
    assert _find(rep, "cost", "deliver") is not None or _find(rep, "per", "deliver") is not None
    assert _find(rep, "latency") is not None
    assert _find(rep, "class") is not None or _find(rep, "effective") is not None
    assert _find(rep, "total") is not None


def test_station_report_sends_count_matches_dispatches():
    sim = _scenario(13)
    _finish(sim)
    rep = _call_report(sim, "station")
    count = _find(rep, "send", "count")
    if count is None:
        count = _find(rep, "sends")
    if isinstance(count, dict):
        count = count.get("total")
    if not isinstance(count, int):
        pytest.skip("precondition not reached: numeric send count not located")
    s1 = len([s for s in sim.sends if s.station_id == "S1"])
    assert count == s1


@pytest.mark.parametrize("seed", [21, 22])
def test_reporting_does_not_change_sending_behaviour(seed):
    def run(with_reports):
        sim = _scenario(seed)
        if with_reports:
            for scope in ("station", "batch", "window"):
                _call_report(sim, scope)
        _finish(sim)
        if with_reports:
            for scope in ("station", "batch", "window"):
                _call_report(sim, scope)
        sends = [(s.station_id, s.price, s.time) for s in sim.sends]
        prices = {s: sim.station_price(s) for s in STATIONS}
        return sends, prices

    # app is a module singleton; run the plain case first, then with reports
    plain = run(False)
    with_rep = run(True)
    assert plain == with_rep


def test_report_does_not_add_events_or_sends():
    sim = _scenario(31)
    n_sends = len(sim.sends)
    n_events = len(sim.events())
    for scope in ("station", "batch", "window"):
        _call_report(sim, scope)
    assert len(sim.sends) == n_sends
    assert len(sim.events()) == n_events
    _finish(sim)
    assert sim.station_price("S1") == 110
    assert sim.station_price("S2") == 50
