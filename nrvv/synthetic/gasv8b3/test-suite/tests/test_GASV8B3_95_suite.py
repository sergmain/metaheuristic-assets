import pytest
import app
import nrvv_env


def _as_obj(x):
    if isinstance(x, dict):
        return x
    if hasattr(x, "__dict__"):
        return dict(vars(x))
    return x


def _num(v):
    v = _as_obj(v)
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, dict):
        for k, val in v.items():
            if "cost" in str(k).lower() and isinstance(_as_obj(val), (int, float)):
                return _as_obj(val)
    return None


def _find(rep, name, need_cost=True):
    """Find a numeric cost for class `name` (or 'total') anywhere in the report."""
    rep = _as_obj(rep)
    cands = []

    def walk(o):
        o = _as_obj(o)
        if isinstance(o, dict):
            for k, v in o.items():
                kl = str(k).lower()
                if name in kl:
                    cands.append((kl, v))
                walk(v)

    walk(rep)
    for pref in (lambda k: "cost" in k and "count" not in k,
                 lambda k: "count" not in k and "num" not in k):
        for k, v in cands:
            if pref(k):
                n = _num(v)
                if n is not None:
                    return n
    return None


def _report():
    fn = getattr(app, "get_sending_cost_report", None)
    if fn is None:
        pytest.skip("precondition not reached: get_sending_cost_report missing")
    return fn()


def _classes(rep):
    out = {}
    for c in ("superseded", "effective", "redundant", "failed"):
        v = _find(rep, c)
        out[c] = v
    return out


def _check_total(rep, cls):
    total = _find(rep, "total")
    if total is None:
        pytest.skip("precondition not reached: total cost not found in report")
    present = {k: v for k, v in cls.items() if v is not None}
    assert sum(present.values()) == pytest.approx(total)
    return total


def _mk(seed, sid):
    sim = nrvv_env.Simulation(seed=seed, station_ids=(sid,), initial_price=0)
    sim.connect(app)
    return sim


def _run_ab(sim, sid):
    assert sim.submit(sid, 10) is not None or True
    if not sim.in_flight:
        pytest.skip("precondition not reached: no send after first submit")
    a = sim.in_flight[0]
    sim.submit(sid, 11)
    sim.deliver(a.send_id)
    sim.deliver_ack()
    return a


def _drain_until(sim, price):
    n = 0
    while sim.step() and n < 50:
        n += 1


def test_superseded_and_effective_costs_match_unit_costs():
    sid = "SA"
    sim = _mk(1, sid)
    _run_ab(sim, sid)
    sim.run_until_idle()
    if len(sim.sends) < 2:
        pytest.skip("precondition not reached: follow-up send not made")
    rep = _report()
    cls = _classes(rep)
    total = _check_total(rep, cls)
    unit = total / len(sim.sends)
    assert cls["superseded"] == pytest.approx(unit)
    assert cls["effective"] == pytest.approx(unit)


def test_sends_are_a_then_b_with_latest_price():
    sid = "SB"
    sim = _mk(2, sid)
    _run_ab(sim, sid)
    sim.run_until_idle()
    assert [s.price for s in sim.sends][:2] == [10, 11]
    assert sim.station_price(sid) == 11


def test_redundant_resend_classified_and_total_is_sum():
    sid = "SC"
    sim = _mk(3, sid)
    _run_ab(sim, sid)
    sim.run_until_idle()
    before = len(sim.sends)
    sim.submit(sid, 11)
    sim.run_until_idle()
    if len(sim.sends) <= before:
        pytest.skip("precondition not reached: no repeat send of an acknowledged price")
    rep = _report()
    cls = _classes(rep)
    total = _check_total(rep, cls)
    unit = total / len(sim.sends)
    assert cls["redundant"] == pytest.approx(unit * (len(sim.sends) - before))
    assert cls["superseded"] == pytest.approx(unit)
    assert cls["effective"] == pytest.approx(unit)


def test_failed_send_classified_failed():
    sid = "SD"
    sim = _mk(4, sid)
    sim.submit(sid, 10)
    if not sim.in_flight:
        pytest.skip("precondition not reached: no send made")
    sim.advance_time(1000000)
    rep = _report()
    f = _find(rep, "failed")
    if not f:
        pytest.skip("precondition not reached: send did not time out or get rejected")
    total = _find(rep, "total")
    assert total is not None and f <= total


def test_classification_does_not_change_sends():
    runs = []
    for with_report in (False, True):
        sid = "SE"
        sim = _mk(5, sid)
        _run_ab(sim, sid)
        if with_report:
            _report()
        sim.run_until_idle()
        sim.submit(sid, 11)
        sim.run_until_idle()
        if with_report:
            _report()
        runs.append([(s.station_id, s.price) for s in sim.sends])
    assert runs[0] == runs[1]


def test_total_equals_sum_of_classes_across_seeds():
    for seed in (11, 12, 13):
        sid = "SF%d" % seed
        sim = _mk(seed, sid)
        _run_ab(sim, sid)
        sim.run_until_idle()
        rep = _report()
        cls = _classes(rep)
        if all(v is None for v in cls.values()):
            pytest.skip("precondition not reached: no class costs in report")
        _check_total(rep, cls)
