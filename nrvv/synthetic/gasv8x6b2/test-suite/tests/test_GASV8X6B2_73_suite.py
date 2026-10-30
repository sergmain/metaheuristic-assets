import pytest
import app
import nrvv_env

_RECORD_GETTERS = (
    "get_cost_records", "get_send_cost_records", "get_cost_record",
    "get_send_cost_record", "cost_records", "send_cost_records", "get_send_records",
)


def _field(rec, names):
    for n in names:
        if isinstance(rec, dict) and n in rec:
            return rec[n]
        if not isinstance(rec, dict) and hasattr(rec, n):
            return getattr(rec, n)
    return None


def _has(rec, names):
    for n in names:
        if isinstance(rec, dict) and n in rec:
            return True
        if not isinstance(rec, dict) and hasattr(rec, n):
            return True
    return False


def _records(station):
    for name in _RECORD_GETTERS:
        g = getattr(app, name, None)
        if g is None:
            continue
        try:
            res = g(station) if callable(g) else g
        except TypeError:
            try:
                res = g()
            except Exception:
                continue
        except Exception:
            continue
        if isinstance(res, dict):
            res = list(res.values())
        if res is None:
            continue
        if not isinstance(res, (list, tuple)):
            res = [res]
        return [r for r in res
                if _field(r, ("station_id", "station")) in (station, None)]
    return None


def _setup(seed, station):
    sim = nrvv_env.Simulation(seed=seed, ordering="fifo", start_time=100.0)
    sim.connect(app)
    return sim


@pytest.mark.parametrize("seed", [1, 2])
def test_send_carries_service_assigned_increasing_version(seed):
    st = "st-ver-%d" % seed
    sim = _setup(seed, st)
    sim.submit(st, 1.50)
    sends1 = [s for s in sim.sends if s["station_id"] == st]
    if not sends1:
        pytest.skip("precondition not reached: no send issued after submit")
    v1 = sends1[0]["version"]
    assert v1 is not None
    assert sends1[0]["request_id"] is not None
    sim.run_until_idle()
    sim.advance(5)
    n = len(sim.sends)
    sim.submit(st, 1.75)
    sim.run_until_idle()
    later = [s for s in sim.sends[n:] if s["station_id"] == st]
    if not later:
        pytest.skip("precondition not reached: no second send issued")
    assert later[0]["version"] > v1


def test_cost_record_exists_with_fields_and_ack_state():
    st = "st-rec-1"
    sim = _setup(3, st)
    sim.submit(st, 2.00)
    sends = [s for s in sim.sends if s["station_id"] == st]
    if not sends:
        pytest.skip("precondition not reached: no send issued after submit")
    send = sends[0]
    recs = _records(st)
    if recs is None:
        pytest.skip("precondition not reached: cost records not queryable")
    match = [r for r in recs if _field(r, ("version", "price_version")) == send["version"]]
    assert match, "no cost record for the version carried by the send"
    rec = match[0]
    assert _field(rec, ("station_id", "station")) in (st, None)
    assert _has(rec, ("request_time", "requested_at", "time"))
    assert _field(rec, ("request_time", "requested_at", "time")) == send["time"]
    attempts = _field(rec, ("attempts", "attempt_count", "attempts_count"))
    assert attempts is not None
    n_att = attempts if isinstance(attempts, int) else len(attempts)
    assert n_att >= 1
    state = str(_field(rec, ("state", "status"))).lower().replace("_", " ")
    assert state == "in flight"
    sim.run_until_idle()
    recs = _records(st)
    rec = [r for r in recs
           if _field(r, ("version", "price_version")) == send["version"]][0]
    state = str(_field(rec, ("state", "status"))).lower().replace("_", " ")
    assert state == "acknowledged"


def test_sending_cost_report_counts_each_send():
    st = "st-cost-1"
    sim = _setup(4, st)
    sim.submit(st, 3.0)
    sim.run_until_idle()
    n = len([s for s in sim.sends if s["station_id"] == st])
    if n == 0:
        pytest.skip("precondition not reached: no send issued")
    report = app.get_sending_cost_report((0.0, sim.now() + 1))
    assert report["sends_count"] >= n
