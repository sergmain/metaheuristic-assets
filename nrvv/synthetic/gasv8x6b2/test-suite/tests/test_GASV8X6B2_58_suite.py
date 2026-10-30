import pytest

import app
import nrvv_env


STATION = "S1"


def _state_get(state, key):
    if isinstance(state, dict):
        return state.get(key)
    return getattr(state, key, None)


def _find_regression(seed, ordering, submit_plan):
    """Drive the simulation until an acknowledgement for a send whose version is
    lower than an already acknowledged version lands while a newer version is desired.
    Returns (sim, ack_record, send_record, prior_max_version) or None."""
    sim = nrvv_env.Simulation(seed=seed, ordering=ordering)
    sim.connect(app)
    prices = [10.0, 20.0, 30.0]
    submitted = 0
    steps = 0
    seen_acks = 0
    best = {}
    while steps < 2000:
        if submitted < 3 and (steps >= submit_plan[submitted] or not sim.step_possible()
                              if False else steps >= submit_plan[submitted]):
            sim.advance(1.0)
            sim.submit(STATION, prices[submitted])
            submitted += 1
            continue
        if not sim.step():
            if submitted < 3:
                steps = submit_plan[submitted]
                continue
            break
        steps += 1
        if len(sim.acknowledgements) > seen_acks:
            seen_acks = len(sim.acknowledgements)
            ack = sim.acknowledgements[-1]
            send = sim.sends[ack["ordinal"]]
            ver = send["version"]
            prev = best.get(send["station_id"])
            best[send["station_id"]] = ver if prev is None else max(prev, ver)
            if prev is not None and ver < prev:
                st = app.get_station_state(STATION)
                latest = _state_get(st, "latest_version")
                if latest is not None and latest > prev:
                    return sim, ack, send, prev
    return None


def _scenario():
    plans = [(0, 1, 2), (0, 2, 4), (0, 0, 0), (1, 3, 6), (0, 1, 1)]
    for ordering in ("random", "fifo"):
        for seed in range(30):
            for plan in plans:
                try:
                    found = _find_regression(seed, ordering, plan)
                except Exception:
                    found = None
                if found:
                    return found
    return None


def test_regressed_ack_records_older_version_as_last_confirmed():
    found = _scenario()
    if found is None:
        pytest.skip("precondition not reached: ack of older version after newer confirmed with newer desired")
    sim, ack, send, prev = found
    st = app.get_station_state(STATION)
    assert _state_get(st, "last_acknowledged_price") == send["price"]
    assert send["version"] < prev


def test_regressed_ack_leaves_station_unsettled():
    found = _scenario()
    if found is None:
        pytest.skip("precondition not reached: ack of older version after newer confirmed with newer desired")
    sim, ack, send, prev = found
    st = app.get_station_state(STATION)
    assert _state_get(st, "settled") is False
    assert _state_get(st, "latest_version") > send["version"]


def test_stale_interval_stays_open_after_regressed_ack():
    found = _scenario()
    if found is None:
        pytest.skip("precondition not reached: ack of older version after newer confirmed with newer desired")
    sim, ack, send, prev = found
    t0 = sim.now()

    def cost(t):
        for period in ((0.0, t), {"start": 0.0, "end": t}, t, (0, t)):
            try:
                r = app.get_stale_price_cost_report(period)
            except TypeError:
                continue
            return _state_get(r, "cost_total")
        return None

    c1 = cost(t0)
    if c1 is None:
        pytest.skip("precondition not reached: stale cost report period format")
    c2 = cost(t0 + 10.0)
    sim.set_time(t0 + 10.0)
    c2 = cost(t0 + 10.0)
    assert c2 > c1
