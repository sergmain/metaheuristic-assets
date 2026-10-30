import pytest

import app
import nrvv_env


def _connect(seed):
    sim = nrvv_env.Simulation(seed=seed, ordering="fifo", cost_per_send=2.0)
    sim.connect(app)
    return sim


def _report(sim, hi=1e9):
    fn = app.get_sending_cost_report
    last = None
    for arg in (None, (0, hi), {"start": 0, "end": hi}, {}):
        try:
            return fn(arg)
        except TypeError as exc:
            last = exc
    raise last


def _walk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k), v
            yield from _walk(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk(v)


def _markers(rep):
    found = set()
    for k, v in _walk(rep):
        kl = k.lower()
        if isinstance(v, bool):
            if "provisional" in kl:
                found.add("provisional" if v else "final")
            elif "final" in kl or "settled" in kl:
                found.add("final" if v else "provisional")
        elif isinstance(v, str):
            vl = v.lower()
            if vl == "provisional":
                found.add("provisional")
            elif vl in ("final", "settled"):
                found.add("final")
    return found


def _has_as_of(rep):
    for k, v in _walk(rep):
        kl = k.lower().replace("-", "_")
        if "as_of" in kl or "asof" in kl:
            return v is not None
    return False


def _submit_and_send(sim, station="S1", price=10.0):
    sim.submit(station, price)
    if not sim.sends:
        pytest.skip("precondition not reached: no send issued after submission")
    sim.step_send()


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_unacknowledged_send_is_provisional_with_as_of(seed):
    sim = _connect(seed)
    _submit_and_send(sim)
    rep = _report(sim)
    assert _markers(rep) == {"provisional"}
    assert _has_as_of(rep)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_acknowledged_record_is_final(seed):
    sim = _connect(seed)
    _submit_and_send(sim)
    assert sim.step_ack()
    rep = _report(sim)
    assert _markers(rep) == {"final"}
    assert _has_as_of(rep)


def test_replayed_acknowledgement_does_not_double_count():
    sim = _connect(5)
    _submit_and_send(sim)
    assert sim.step_ack()
    before = _report(sim)
    ack = sim.acknowledgements[-1]
    app.on_acknowledgement(ack["station_id"], ack["request_id"], "ok")
    app.on_acknowledgement(ack["station_id"], ack["request_id"], "ok")
    after = _report(sim)
    assert after["cost_total"] == before["cost_total"]
    assert after["sends_count"] == before["sends_count"]
    assert _markers(after) == {"final"}


def test_final_figures_unchanged_by_later_report():
    sim = _connect(7)
    _submit_and_send(sim)
    assert sim.step_ack()
    first = _report(sim)
    sim.advance(100)
    second = _report(sim)
    assert second["cost_total"] == first["cost_total"]
    assert second["sends_count"] == first["sends_count"]
    assert second.get("cost_per_station") == first.get("cost_per_station")
    assert _markers(second) == {"final"}


def test_final_station_figure_stable_while_other_station_in_flight():
    sim = _connect(9)
    _submit_and_send(sim, "S1", 10.0)
    assert sim.step_ack()
    first = _report(sim)
    n = len(sim.sends)
    sim.advance(5)
    sim.submit("S2", 12.0)
    if len(sim.sends) == n:
        pytest.skip("precondition not reached: no send for second station")
    sim.step_send()
    later = _report(sim)
    assert _markers(later) == {"final", "provisional"}
    per_first = first.get("cost_per_station")
    per_later = later.get("cost_per_station")
    if isinstance(per_first, dict) and isinstance(per_later, dict):
        assert per_later["S1"] == per_first["S1"]
