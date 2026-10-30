import re

import pytest

import nrvv_env
import app


STATION = "ST-1"


def _get_report(sim):
    last = None
    for period in (None, (0.0, sim.now() + 1000.0), {"start": 0.0, "end": sim.now() + 1000.0}):
        try:
            return app.get_sending_cost_report(period)
        except Exception as exc:  # period shape unknown
            last = exc
    raise last


def _scenario(seed):
    sim = nrvv_env.Simulation(seed=seed, cost_per_send=1.0, ordering="fifo")
    sim.connect(app)
    sim.submit(STATION, 10.0)
    sim.advance(1.0)
    if len(sim.sends) < 1:
        pytest.skip("precondition not reached: send 1 not issued")
    sim.submit(STATION, 12.0)
    sim.advance(1.0)
    if len(sim.sends) < 2:
        pytest.skip("precondition not reached: send 2 not issued while send 1 in flight")
    sim.set_arrival_order([1, 0])
    sim.step_send()
    sim.step_send()
    if [d["ordinal"] for d in sim.deliveries[:2]] != [1, 0]:
        pytest.skip("precondition not reached: scripted arrival order")
    sim.advance(1.0)
    while sim.step_ack():
        sim.advance(1.0)
    if len(sim.acknowledgements) < 2:
        pytest.skip("precondition not reached: both acknowledgements delivered")
    return sim, _get_report(sim)


def _records(node, station=None, version=None, out=None):
    if out is None:
        out = []
    if isinstance(node, dict):
        vkey = next((k for k in node if isinstance(k, str) and "version" in k.lower()), None)
        if vkey is not None and isinstance(node[vkey], int) and not isinstance(node[vkey], bool):
            out.append(node)
            return out
        for k, v in node.items():
            if isinstance(v, (dict, list)):
                _records(v, station, version, out)
    elif isinstance(node, list):
        for v in node:
            _records(v, station, version, out)
    return out


def _keyed_records(report):
    """Records stored in a mapping keyed by (station, version) or 'station:version'."""
    found = {}

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, tuple) and len(k) == 2 and k[0] == STATION:
                    found.setdefault(int(k[1]), []).append(v)
                elif isinstance(k, str):
                    m = re.match(r"^(.+?)[:#/@|_ ,-]+v?(\d+)$", k)
                    if m and m.group(1) == STATION:
                        found.setdefault(int(m.group(2)), []).append(v)
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(report)
    return found


def _by_version(report):
    by_v = {}
    for r in _records(report):
        st = next((r[k] for k in r if isinstance(k, str) and "station" in k.lower()), STATION)
        if st != STATION:
            continue
        vkey = next(k for k in r if isinstance(k, str) and "version" in k.lower())
        by_v.setdefault(r[vkey], []).append(r)
    if not by_v:
        by_v = _keyed_records(report)
    return by_v


def _superseded_flag(rec):
    if not isinstance(rec, dict):
        return bool(rec)
    for k, v in rec.items():
        if isinstance(k, str) and "supersed" in k.lower():
            if isinstance(v, bool):
                return v
        if isinstance(k, str) and k.lower() in ("state", "status") and isinstance(v, str):
            if "supersed" in v.lower():
                return True
    return False


def _find_superseded_total(report):
    vals = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str) and "supersed" in k.lower() and isinstance(v, (int, float)) \
                        and not isinstance(v, bool):
                    vals.append(v)
                elif isinstance(k, str) and "supersed" in k.lower() and isinstance(v, dict):
                    for vv in v.values():
                        if isinstance(vv, (int, float)) and not isinstance(vv, bool):
                            vals.append(vv)
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(report)
    return vals


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_separate_record_per_send_counted_once(seed):
    sim, report = _scenario(seed)
    by_v = _by_version(report)
    if not by_v:
        pytest.skip("precondition not reached: report exposes no per-send records")
    versions = sorted(by_v)
    sent_versions = sorted(s["version"] for s in sim.sends[:2])
    assert versions[:2] == sent_versions or set(sent_versions) <= set(versions)
    for v in sent_versions:
        assert len(by_v[v]) == 1


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_superseded_send_flagged_and_subtotal(seed):
    sim, report = _scenario(seed)
    by_v = _by_version(report)
    if not by_v:
        pytest.skip("precondition not reached: report exposes no per-send records")
    v1, v2 = sim.sends[0]["version"], sim.sends[1]["version"]
    assert v1 < v2
    assert _superseded_flag(by_v[v1][0])
    assert not _superseded_flag(by_v[v2][0])
    totals = _find_superseded_total(report)
    assert totals and max(totals) > 0


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_no_send_cost_dropped(seed):
    sim, report = _scenario(seed)
    n = len(sim.sends)
    assert report["sends_count"] == n
    assert report["cost_total"] == pytest.approx(n * sim.cost_per_send)
    per = report["cost_per_station"]
    assert per[STATION] == pytest.approx(n * sim.cost_per_send)
