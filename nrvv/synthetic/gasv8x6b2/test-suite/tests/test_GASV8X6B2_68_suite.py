import pytest
import nrvv_env
import app


def _walk(obj):
    yield obj
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk(v)


def _records(report):
    out = []
    for d in _walk(report):
        if not isinstance(d, dict):
            continue
        vkeys = [k for k in d if "version" in str(k).lower()]
        skeys = [k for k in d if "superseded" in str(k).lower() and isinstance(d[k], bool)]
        if vkeys and skeys:
            out.append((d[vkeys[0]], d[skeys[0]], d))
    return out


def _query(sim):
    for period in (None, (0, sim.now()), {"start": 0, "end": sim.now()}):
        try:
            return app.get_sending_cost_report(period)
        except TypeError:
            continue
    return app.get_sending_cost_report(None)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_overlapping_out_of_order_sends_have_separate_counted_records(seed):
    sim = nrvv_env.Simulation(seed=seed, cost_per_send=2.0, ordering="fifo")
    sim.connect(app)
    sid = "S1"
    sim.submit(sid, 10.0)
    sim.advance(1)
    sim.submit(sid, 11.0)
    sim.advance(1)
    if len(sim.sends) < 2:
        pytest.skip("precondition not reached: second send issued while first in flight")
    sim.set_arrival_order([1, 0])
    assert sim.step_send()
    assert sim.step_send()
    assert [d["ordinal"] for d in sim.deliveries][:2] == [1, 0]
    assert sim.step_ack()
    assert sim.step_ack()
    sim.advance(1)

    report = _query(sim)
    n = len(sim.sends)
    assert report["sends_count"] == n
    assert report["cost_total"] == pytest.approx(2.0 * n)
    assert report["cost_per_station"][sid] == pytest.approx(2.0 * n)

    v1 = sim.sends[0]["version"]
    v2 = sim.sends[1]["version"]
    recs = _records(report)
    assert recs, "no per-send records with superseded flag in report"
    by_version = {}
    for ver, sup, d in recs:
        by_version.setdefault(ver, []).append((sup, d))
    assert len(by_version.get(v1, [])) == 1
    assert len(by_version.get(v2, [])) >= 1
    assert by_version[v1][0][0] is True
    assert by_version[v2][0][0] is False

    sub = []
    for d in _walk(report):
        if isinstance(d, dict):
            for k, v in d.items():
                if "superseded" in str(k).lower() and isinstance(v, (int, float)) \
                        and not isinstance(v, bool):
                    sub.append(v)
    assert sub, "no superseded sub-total in report"
    assert max(sub) > 0
