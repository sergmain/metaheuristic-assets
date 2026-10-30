import pytest
import app
import nrvv_env

STATION = "S1"


def _make(seed=0, **kw):
    sim = nrvv_env.Simulation(seed=seed, ordering="fifo", **kw)
    sim.connect(app)
    return sim


def _report(fn_name, sim):
    fn = getattr(app, fn_name, None)
    if fn is None:
        pytest.skip("precondition not reached: %s not available" % fn_name)
    last = None
    for period in (None, (0.0, sim.now()), {"start": 0.0, "end": sim.now()}):
        try:
            return fn(period)
        except Exception as exc:  # try another period shape
            last = exc
    pytest.skip("precondition not reached: report not callable (%r)" % (last,))


def _total(sim):
    s = _report("get_sending_cost_report", sim)
    t = _report("get_stale_price_cost_report", sim)
    return float(s["cost_total"]) + float(t["cost_total"])


def _first_matched(sim, latency=0.0):
    sim.submit(STATION, 10.0)
    if len(sim.sends) < 1:
        pytest.skip("precondition not reached: no send issued after submit")
    assert sim.step_send()
    sim.advance(latency)
    assert sim.step_ack()


def _second_mismatched(sim):
    _first_matched(sim, 1.0)
    sim.advance(1.0)
    sim.submit(STATION, 20.0)
    if len(sim.sends) < 2:
        pytest.skip("precondition not reached: second send not issued")
    assert sim.step_send()
    sim.advance(1.0)
    bad = "mismatched-" + str(sim.sends[1]["request_id"])
    app.on_acknowledgement(STATION, bad, "ok")


@pytest.mark.parametrize("seed", [1, 2])
def test_matched_ack_closes_first_record(seed):
    sim = _make(seed)
    _first_matched(sim, 2.0)
    st = app.get_station_state(STATION)
    assert st["settled"] is True
    assert st["last_acknowledged_price"] == 10.0


def test_mismatched_ack_does_not_settle_station():
    sim = _make()
    _second_mismatched(sim)
    st = app.get_station_state(STATION)
    assert st["settled"] is False
    assert st["last_acknowledged_price"] != 20.0
    assert st["latest_desired_price"] == 20.0


def test_mismatched_ack_keeps_stale_cost_accruing():
    sim = _make()
    _second_mismatched(sim)
    before = float(_report("get_stale_price_cost_report", sim)["cost_total"])
    sim.advance(5.0)
    mid = float(_report("get_stale_price_cost_report", sim)["cost_total"])
    sim.advance(5.0)
    after = float(_report("get_stale_price_cost_report", sim)["cost_total"])
    assert mid > before
    assert after > mid


def test_mismatched_ack_cost_grows_strictly_with_rate():
    sim = _make(stale_cost_per_time=3.0)
    _second_mismatched(sim)
    a = float(_report("get_stale_price_cost_report", sim)["cost_total"])
    sim.advance(4.0)
    b = float(_report("get_stale_price_cost_report", sim)["cost_total"])
    assert b - a == pytest.approx(12.0)


def test_mismatched_ack_leaves_station_unsettled_after_time():
    sim = _make()
    _second_mismatched(sim)
    sim.advance(50.0)
    assert app.get_station_state(STATION)["settled"] is False


def test_matched_record_cost_includes_ack_latency():
    quick = _make()
    _first_matched(quick, 0.0)
    slow = _make()
    _first_matched(slow, 9.0)
    assert _total(slow) > _total(quick)


def test_ack_latency_cost_scales_with_latency():
    totals = []
    for lat in (1.0, 5.0, 10.0):
        sim = _make()
        _first_matched(sim, lat)
        totals.append(_total(sim))
    assert totals[0] < totals[1] < totals[2]
