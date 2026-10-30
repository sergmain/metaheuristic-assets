import pytest
import app
import nrvv_env

STATION = "S1"
RATE = 2.5


def _report(sim):
    last = None
    for period in (None, (0, sim.now() + 1000), {"start": 0, "end": sim.now() + 1000}):
        try:
            return app.get_sending_cost_report(period)
        except TypeError as exc:
            last = exc
    raise last


def _walk(obj, path=()):
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, path + (str(k),))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _walk(v, path + (str(i),))


def _records(report):
    recs = []
    for _, o in _walk(report):
        if isinstance(o, dict) and ("version" in o or "price_version" in o):
            recs.append(o)
    return recs


def _version(rec):
    return rec["version"] if "version" in rec else rec["price_version"]


def _flag(rec):
    for k, v in rec.items():
        if "superseded" in str(k).lower():
            return bool(v)
    raise AssertionError("record has no superseded flag: %r" % (rec,))


def _scenario(seed, arrival):
    sim = nrvv_env.Simulation(seed=seed, cost_per_send=RATE, ordering="random")
    sim.connect(app)
    sim.submit(STATION, 10.0)
    if len(sim.sends) < 1:
        pytest.skip("precondition not reached: send 1 not issued")
    sim.advance(1)
    sim.submit(STATION, 11.0)
    if len(sim.sends) < 2:
        pytest.skip("precondition not reached: send 2 issued while send 1 in flight")
    sim.set_arrival_order(arrival)
    sim.advance(1)
    sim.step_send()
    sim.step_send()
    sim.advance(1)
    while sim.step_ack():
        sim.advance(1)
    return sim


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("arrival", [[1, 0], [0, 1]])
def test_separate_record_per_send_with_superseded_flag(seed, arrival):
    sim = _scenario(seed, arrival)
    assert [d["ordinal"] for d in sim.deliveries] == arrival
    v1 = sim.sends[0]["version"]
    v2 = sim.sends[1]["version"]
    assert v1 != v2
    report = _report(sim)
    assert report["sends_count"] == 2
    assert report["cost_total"] == pytest.approx(2 * RATE)
    cps = report["cost_per_station"]
    val = cps[STATION] if isinstance(cps, dict) else cps
    if isinstance(val, dict):
        nums = [x for _, x in _walk(val) if isinstance(x, (int, float)) and not isinstance(x, bool)]
        assert 2 * RATE in [pytest.approx(n) and n for n in nums] or any(
            n == pytest.approx(2 * RATE) for n in nums)
    else:
        assert val == pytest.approx(2 * RATE)

    recs = [r for r in _records(report)]
    by_version = {}
    for r in recs:
        by_version.setdefault(_version(r), []).append(r)
    assert set(by_version) >= {v1, v2}
    assert len(by_version[v1]) == 1 and len(by_version[v2]) == 1
    assert _flag(by_version[v1][0]) is True
    assert _flag(by_version[v2][0]) is False

    sub = []
    rec_ids = {id(r) for r in recs}
    for path, o in _walk(report):
        if any("superseded" in p.lower() for p in path) and not isinstance(o, (dict, list, tuple)):
            if isinstance(o, (int, float)) and not isinstance(o, bool):
                if not any(id(r) in rec_ids for r in recs if path and False):
                    sub.append(o)
    assert any(n == pytest.approx(RATE) for n in sub), "no distinct superseded sub-total of one send"
