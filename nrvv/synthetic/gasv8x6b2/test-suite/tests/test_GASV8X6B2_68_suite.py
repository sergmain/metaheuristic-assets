import pytest

import app
import nrvv_env

COST = 2.5
STATION = "S1"


def _setup(seed, arrival):
    sim = nrvv_env.Simulation(seed=seed, cost_per_send=COST, stale_cost_per_time=1.0,
                              ordering="fifo")
    sim.connect(app)
    sim.submit(STATION, 10.0)
    sim.advance(1.0)
    sim.submit(STATION, 12.0)
    if len(sim.sends) < 2:
        pytest.skip("precondition not reached: two overlapping sends were not issued")
    sim.set_arrival_order(arrival)
    assert sim.step_send()
    assert sim.step_send()
    assert sim.step_ack()
    assert sim.step_ack()
    sim.advance(1.0)
    return sim


def _report(sim):
    try:
        return app.get_sending_cost_report(None)
    except Exception:
        return app.get_sending_cost_report((0.0, sim.now()))


def _walk(obj, out, keys):
    if isinstance(obj, dict):
        st = next((obj[k] for k in ("station_id", "station") if k in obj), None)
        ver = next((obj[k] for k in ("version", "price_version") if k in obj), None)
        if st is not None and ver is not None:
            out.append(obj)
        for k, v in obj.items():
            if isinstance(k, tuple) and len(k) == 2 and isinstance(v, dict):
                rec = dict(v)
                rec.setdefault("station_id", k[0])
                rec.setdefault("version", k[1])
                out.append(rec)
            keys.append((k, v))
            _walk(v, out, keys)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk(v, out, keys)


def _check(sim):
    rep = _report(sim)
    recs, kv = [], []
    _walk(rep, recs, kv)
    by_id = {}
    for r in recs:
        st = next(r[k] for k in ("station_id", "station") if k in r)
        ver = next(r[k] for k in ("version", "price_version") if k in r)
        by_id.setdefault((st, ver), []).append(r)
    v1 = sim.sends[0]["version"]
    v2 = sim.sends[1]["version"]
    assert v1 != v2
    assert (STATION, v1) in by_id and (STATION, v2) in by_id
    assert len(by_id[(STATION, v1)]) == 1 and len(by_id[(STATION, v2)]) == 1
    assert len(by_id) == 2

    def flag(r):
        for k, v in r.items():
            if "supersed" in str(k).lower() and not isinstance(v, (dict, list)):
                return bool(v)
        raise AssertionError("record has no superseded flag")

    assert flag(by_id[(STATION, v1)][0]) is True
    assert flag(by_id[(STATION, v2)][0]) is False

    assert rep["sends_count"] == 2
    assert rep["cost_total"] == pytest.approx(2 * COST)
    assert rep["cost_per_station"][STATION] == pytest.approx(2 * COST)

    sub = [v for k, v in kv if "supersed" in str(k).lower()
           and not isinstance(k, tuple)]
    nums = []
    for v in sub:
        if isinstance(v, dict):
            nums.extend(x for x in v.values() if isinstance(x, (int, float)))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            nums.append(v)
    assert any(n == pytest.approx(COST) or n == 1 for n in nums), \
        "no distinct superseded sub-total of one send"


def test_reordered_arrival_separate_records_and_superseded_subtotal():
    _check(_setup(1, [1, 0]))


def test_issue_order_arrival_same_attribution():
    _check(_setup(2, [0, 1]))


def test_reordered_arrival_other_seed():
    _check(_setup(7, [1, 0]))
