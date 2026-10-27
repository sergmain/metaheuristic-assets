import pytest
import app
import nrvv_env


def _records_fn():
    for name in dir(app):
        low = name.lower()
        if name.startswith("_"):
            continue
        if "cost" in low and "record" in low and callable(getattr(app, name)):
            return getattr(app, name)
    return None


def _get(rec, *names):
    for n in names:
        if isinstance(rec, dict):
            if n in rec:
                return rec[n]
        elif hasattr(rec, n):
            return getattr(rec, n)
    raise AssertionError("record lacks any of %r: %r" % (names, rec))


def _has(rec, *names):
    try:
        _get(rec, *names)
        return True
    except AssertionError:
        return False


def _scenario(seed):
    sim = nrvv_env.Simulation(seed=seed, station_ids=("S1",), initial_price=0)
    sim.connect(app)
    sim.submit("S1", 10)
    sim.submit("S1", 11)  # arrives while the first send is in flight
    sim.submit("S1", 12)
    sim.run_until_idle()
    # try to provoke a resend after a long silence
    sim.submit("S1", 13)
    sim.advance_time(100000)
    sim.step()
    sim.advance_time(100000)
    sim.run_until_idle()
    return sim


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_one_cost_record_per_send_with_required_fields(seed):
    fn = _records_fn()
    if fn is None:
        pytest.skip("precondition not reached: no cost record query on app")
    sim = _scenario(seed)
    assert len(sim.sends) >= 2
    recs = list(fn())
    assert len(recs) == len(sim.sends)
    ids = [_get(r, "send_id", "sendId", "id") for r in recs]
    assert len(set(ids)) == len(ids)
    assert set(ids) == {s.send_id for s in sim.sends}
    by_id = {_get(r, "send_id", "sendId", "id"): r for r in recs}
    for s in sim.sends:
        r = by_id[s.send_id]
        assert _get(r, "station", "station_id", "stationId") == s.station_id
        assert _get(r, "price") == s.price
        assert _has(r, "generation", "desired_generation", "version", "desired_version")
        assert _get(r, "dispatch_time", "dispatched_at", "dispatch") == s.time
        assert _has(r, "message_count", "messages", "num_messages")
        assert _has(r, "payload_size", "payload_bytes", "size")
        assert _has(r, "unit_cost", "cost_per_message")


def test_resolved_records_have_resolution_time_and_outcome():
    fn = _records_fn()
    if fn is None:
        pytest.skip("precondition not reached: no cost record query on app")
    sim = _scenario(7)
    recs = list(fn())
    resolved = 0
    for r in recs:
        outcome = _get(r, "outcome", "resolution", "status")
        if outcome is not None:
            resolved += 1
            assert _get(r, "resolution_time", "resolved_at", "resolved_time") is not None
    assert resolved >= 1


def test_resend_links_to_original_and_records_survive_restart():
    fn = _records_fn()
    if fn is None:
        pytest.skip("precondition not reached: no cost record query on app")
    sim = _scenario(5)
    recs = list(fn())
    linked = [r for r in recs
              if _has(r, "original_send_id", "original", "linked_to", "parent_send_id", "resend_of")
              and _get(r, "original_send_id", "original", "linked_to", "parent_send_id", "resend_of") is not None]
    if not linked:
        pytest.skip("precondition not reached: no resend produced through nrvv_env")
    ids = {_get(r, "send_id", "sendId", "id") for r in recs}
    for r in linked:
        assert _get(r, "original_send_id", "original", "linked_to", "parent_send_id", "resend_of") in ids
    before = sorted(str(_get(r, "send_id", "sendId", "id")) for r in recs)
    restart = getattr(app, "restart", None)
    if not callable(restart):
        pytest.skip("precondition not reached: no restart operation on app")
    restart()
    sim.connect(app)
    after = sorted(str(_get(r, "send_id", "sendId", "id")) for r in fn())
    assert before == after[:len(before)] or set(before) <= set(after)
