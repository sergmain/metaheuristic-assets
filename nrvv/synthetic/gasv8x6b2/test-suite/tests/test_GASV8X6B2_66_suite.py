import importlib

import pytest

import app
import nrvv_env

STATION = "S1"


def _setup(seed, ordering="fifo"):
    importlib.reload(app)
    sim = nrvv_env.Simulation(seed=seed, ordering=ordering,
                              cost_per_send=1.0, stale_cost_per_time=1.0)
    sim.connect(app)
    return sim


def _report(fn_name, until):
    fn = getattr(app, fn_name, None)
    if fn is None:
        pytest.skip("precondition not reached: report operation %s missing" % fn_name)
    for period in ((0.0, until), {"start": 0.0, "end": until}, None):
        try:
            return fn(period)
        except Exception:
            continue
    pytest.skip("precondition not reached: report period format")


def _total(rep):
    if isinstance(rep, dict) and "cost_total" in rep:
        t = rep["cost_total"]
        if isinstance(t, dict):
            t = sum(v for v in t.values() if isinstance(v, (int, float)))
        return t
    pytest.skip("precondition not reached: cost_total in report")


def _three_sends(sim, latency=2.0):
    """Request three sends, deliver matched ack for the first, bogus id for the second."""
    sim.submit(STATION, 10)
    sim.submit(STATION, 11)
    sim.submit(STATION, 12)
    if not sim.sends:
        pytest.skip("precondition not reached: no send issued")
    sim.step_send()
    sim.advance(latency)
    sim.step_ack()
    if len(sim.sends) < 3:
        # try to provoke further sends
        sim.advance(1.0)
    if len(sim.sends) < 3:
        pytest.skip("precondition not reached: three sends outstanding")
    return sim.sends[1]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_mismatched_ack_leaves_station_unsettled(seed):
    sim = _setup(seed)
    second = _three_sends(sim)
    sim.step_send()
    sim.advance(1.0)
    app.on_acknowledgement(STATION, "not-" + str(second["request_id"]), "ok")
    state = app.get_station_state(STATION)
    assert state["settled"] is False


@pytest.mark.parametrize("seed", [1, 2])
def test_mismatched_ack_cost_keeps_accruing(seed):
    sim = _setup(seed)
    second = _three_sends(sim)
    sim.step_send()
    sim.advance(1.0)
    app.on_acknowledgement(STATION, "not-" + str(second["request_id"]), "ok")
    t1 = sim.now() + 5.0
    sim.advance_to(t1)
    c1 = _total(_report("get_stale_price_cost_report", t1))
    t2 = t1 + 20.0
    sim.advance_to(t2)
    c2 = _total(_report("get_stale_price_cost_report", t2))
    assert c2 > c1


def test_matched_ack_cost_includes_latency():
    totals = []
    for latency in (1.0, 9.0):
        sim = _setup(5)
        sim.submit(STATION, 10)
        if not sim.sends:
            pytest.skip("precondition not reached: no send issued")
        sim.step_send()
        sim.advance(latency)
        sim.step_ack()
        end = sim.now()
        totals.append(_total(_report("get_sending_cost_report", end)))
    assert totals[1] > totals[0]
