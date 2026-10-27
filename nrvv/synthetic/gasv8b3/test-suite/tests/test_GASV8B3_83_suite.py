import dataclasses

import pytest

import app
import nrvv_env


def _flatten(obj, prefix="", out=None, depth=0):
    if out is None:
        out = {}
    if depth > 6:
        return out
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        obj = dataclasses.asdict(obj)
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(v, prefix + "/" + str(k), out, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _flatten(v, prefix + "/" + str(i), out, depth + 1)
    elif isinstance(obj, (int, float, str, bool)) or obj is None:
        out[prefix] = obj
    elif hasattr(obj, "__dict__"):
        for k, v in vars(obj).items():
            if not k.startswith("_"):
                _flatten(v, prefix + "/" + k, out, depth + 1)
    return out


def _report():
    return _flatten(app.get_sending_cost_report())


def _unattributed(rep):
    vals = [v for k, v in rep.items()
            if "unattributed" in k.lower() and isinstance(v, (int, float))]
    return vals


def _without_unattributed(rep):
    return {k: v for k, v in rep.items() if "unattributed" not in k.lower()}


def _send_count(rep):
    for k, v in rep.items():
        name = k.split("/")[-1].lower()
        if len(k.split("/")) == 2 and name in (
                "number_of_sends", "sends", "send_count", "num_sends",
                "n_sends", "total_sends", "sends_count") and isinstance(v, int):
            return v
    return None


def _setup(seed, stations):
    sim = nrvv_env.Simulation(seed=seed, station_ids=stations, initial_price=0)
    sim.connect(app)
    return sim


def _dispatch_three(seed):
    stations = ["S1", "S2", "S3"]
    sim = _setup(seed, stations)
    for i, s in enumerate(stations):
        sim.submit(s, 10 + i)
    if len(sim.sends) != 3:
        pytest.skip("precondition not reached: one send per station dispatched")
    return sim


def _deliver_reversed_and_ack(sim):
    sent = list(sim.sends)
    for rec in reversed(sent):
        sim.deliver(rec.send_id, rec.station_id)
    while sim.pending_acks:
        sim.deliver_ack()
    return sent


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_unmatched_and_duplicate_acks_counted_unattributed(seed):
    sim = _dispatch_three(seed)
    sent = _deliver_reversed_and_ack(sim)
    assert [a.send_id for a in sim.acknowledgements] != [r.send_id for r in sent]
    before = _report()
    app.on_acknowledgement("S1", "no-such-send-1", 99)
    app.on_acknowledgement("S2", "no-such-send-2", 98)
    dup = sim.acknowledgements[0]
    app.on_acknowledgement(dup.station_id, dup.send_id, dup.reported_price)
    after = _report()
    un = _unattributed(after)
    assert un, "no unattributed acknowledgement count reported"
    assert max(un) - (max(_unattributed(before)) if _unattributed(before) else 0) == 3


@pytest.mark.parametrize("seed", [1, 2])
def test_unattributed_acks_charged_to_no_send(seed):
    sim = _dispatch_three(seed)
    _deliver_reversed_and_ack(sim)
    before = _without_unattributed(_report())
    app.on_acknowledgement("S1", "bogus", 77)
    dup = sim.acknowledgements[1]
    app.on_acknowledgement(dup.station_id, dup.send_id, dup.reported_price)
    after = _without_unattributed(_report())
    assert before == after


@pytest.mark.parametrize("seed", [4, 5])
def test_out_of_order_acks_keep_all_sends_in_cost(seed):
    sim = _dispatch_three(seed)
    _deliver_reversed_and_ack(sim)
    rep = _report()
    n = _send_count(rep)
    if n is None:
        pytest.skip("precondition not reached: send count readable from report")
    assert n == 3
    for s, p in (("S1", 10), ("S2", 11), ("S3", 12)):
        st = app.get_station_state(s)
        flat = _flatten(st)
        assert p in flat.values()


def test_obsolete_send_cost_recorded_in_full():
    sim = _setup(7, ["S1"])
    sim.submit("S1", 10)
    if len(sim.sends) != 1:
        pytest.skip("precondition not reached: first send dispatched")
    first = sim.sends[0]
    sim.submit("S1", 20)
    sim.deliver(first.send_id, "S1")
    sim.run_until_idle()
    rep = _report()
    n = _send_count(rep)
    if n is None:
        pytest.skip("precondition not reached: send count readable from report")
    assert n == len(sim.sends)
    assert n >= 2
    assert sim.station_price("S1") == 20
    before = _without_unattributed(rep)
    app.on_acknowledgement("S1", first.send_id, 10)
    assert _without_unattributed(_report()) == before
    assert max(_unattributed(_report()) or [0]) >= 1
