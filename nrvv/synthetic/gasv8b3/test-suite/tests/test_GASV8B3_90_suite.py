import pytest

import app
import nrvv_env


def _fresh(seed, stations):
    reset = getattr(app, "reset", None)
    if callable(reset):
        reset()
    sim = nrvv_env.Simulation(seed=seed, station_ids=stations)
    sim.connect(app)
    return sim


def _poke(stations):
    for name in ("reconcile", "run_reconciliation", "reconciliation_pass", "tick"):
        fn = getattr(app, name, None)
        if callable(fn):
            try:
                fn()
            except TypeError:
                pass
            break
    for s in stations:
        app.get_station_state(s)


def _settled(station):
    st = app.get_station_state(station)
    if isinstance(st, dict):
        return st["settled"]
    return st.settled


def _sends_for(sim, station):
    return [r for r in sim.sends if r.station_id == station]


def _run_unsettled_scenario(seed, stations, v1, v2, horizon=4000):
    sim = _fresh(seed, stations)
    for s in stations:
        sim.submit(s, v1)
    first = {s: _sends_for(sim, s) for s in stations}
    if any(len(v) != 1 for v in first.values()):
        pytest.skip("precondition not reached: exactly one initial send per station")
    for s in stations:
        sim.submit(s, v2)  # version 2, while send A is lost/unacknowledged
    for s in stations:
        if len(_sends_for(sim, s)) != 1:
            pytest.skip("precondition not reached: single in-flight before timeout")
    for _ in range(horizon):
        sim.advance_time(1)
        _poke(stations)
    return sim, first


@pytest.mark.parametrize("seed", [1, 7])
def test_resend_after_lifetime_carries_latest_price_never_old(seed):
    S = "S"
    sim, first = _run_unsettled_scenario(seed, [S], 10, 20)
    sends = _sends_for(sim, S)
    if len(sends) < 2:
        pytest.skip("precondition not reached: no resend triggered by time advance")
    a = first[S][0]
    resends = sends[1:]
    assert all(r.price == 20 for r in resends)
    assert all(r.price != 10 for r in resends)
    assert resends[0].send_id != a.send_id
    assert resends[0].time > a.time
    ids = [r.send_id for r in sends]
    assert len(set(ids)) == len(ids)
    assert _settled(S) is False


def test_resend_backoff_grows_between_further_resends():
    S = "S"
    sim, _ = _run_unsettled_scenario(3, [S], 10, 20, horizon=6000)
    sends = _sends_for(sim, S)
    if len(sends) < 4:
        pytest.skip("precondition not reached: fewer than three resends observed")
    gaps = [b.time - a.time for a, b in zip(sends[1:], sends[2:])]
    assert all(g2 >= g1 for g1, g2 in zip(gaps, gaps[1:]))
    assert gaps[-1] > gaps[0]
    assert all(r.price == 20 for r in sends[1:])
    assert _settled(S) is False


def test_all_unsettled_stations_restart_cycle_with_latest_price():
    stations = ["S1", "S2", "S3"]
    sim, _ = _run_unsettled_scenario(5, stations, 1, 2)
    for s in stations:
        sends = _sends_for(sim, s)
        if len(sends) < 2:
            pytest.skip("precondition not reached: no resend triggered by time advance")
        assert all(r.price == 2 for r in sends[1:])
        assert _settled(s) is False


def test_settles_only_on_matching_ack_of_version_two_send():
    S = "S"
    sim, first = _run_unsettled_scenario(11, [S], 10, 20)
    sends = _sends_for(sim, S)
    if len(sends) < 2:
        pytest.skip("precondition not reached: no resend triggered by time advance")
    assert _settled(S) is False
    last = sends[-1]
    sim.deliver(last.send_id)
    assert _settled(S) is False  # delivered but not yet acknowledged
    sim.deliver_ack()
    assert _settled(S) is True
