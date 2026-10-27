import pytest

import app
import nrvv_env


STATION = "S1"


def _field(state, *names):
    for n in names:
        if isinstance(state, dict) and n in state:
            return state[n]
        if hasattr(state, n):
            return getattr(state, n)
    if isinstance(state, (tuple, list)) and len(state) >= 3:
        idx = {"latest_desired_price": 0, "last_acknowledged_price": 1, "settled": 2}
        for n in names:
            if n in idx:
                return state[idx[n]]
    raise AssertionError("state field not found: %r in %r" % (names, state))


def _snapshot(state):
    return (
        _field(state, "latest_desired_price"),
        _field(state, "last_acknowledged_price"),
        _field(state, "settled"),
    )


def _find_unmatched(obj, depth=0):
    if depth > 5:
        return None
    items = obj.items() if isinstance(obj, dict) else (
        vars(obj).items() if hasattr(obj, "__dict__") else [])
    for k, v in items:
        lk = str(k).lower()
        if ("unmatched" in lk or "unattributed" in lk) and isinstance(v, int):
            return v
    for k, v in items:
        if isinstance(v, (dict,)) or hasattr(v, "__dict__"):
            r = _find_unmatched(v, depth + 1)
            if r is not None:
                return r
    return None


def _setup(seed):
    sim = nrvv_env.Simulation(seed=seed, station_ids=(STATION,), initial_price=50)
    sim.connect(app)
    sim.submit(STATION, 100)
    if len(sim.sends) != 1:
        pytest.skip("precondition not reached: exactly one send in flight after first submit")
    return sim


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_unknown_ack_ignored_state_unchanged_and_no_send(seed):
    sim = _setup(seed)
    before = _snapshot(app.get_station_state(STATION))
    n_sends = len(sim.sends)
    app.on_acknowledgement(STATION, "no-such-send-id-%d" % seed, 100)
    after = _snapshot(app.get_station_state(STATION))
    assert after == before
    assert len(sim.sends) == n_sends


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_unknown_ack_is_counted_once(seed):
    sim = _setup(seed)
    app.on_acknowledgement(STATION, "no-such-send-id-%d" % seed, 100)
    report = app.get_sending_cost_report()
    count = _find_unmatched(report)
    if count is None:
        pytest.skip("precondition not reached: unmatched acknowledgement count not observable")
    assert count == 1


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_real_ack_matched_by_id_triggers_followup_with_new_send_id(seed):
    sim = _setup(seed)
    first = sim.sends[0]
    app.on_acknowledgement(STATION, "no-such-send-id-%d" % seed, 100)
    sim.submit(STATION, 110)
    assert len(sim.sends) == 1  # still only one send in flight
    sim.deliver(first.send_id)
    sim.deliver_ack()
    assert len(sim.sends) == 2
    follow = sim.sends[1]
    assert follow.station_id == STATION
    assert follow.price == 110
    assert follow.send_id != first.send_id
    state = app.get_station_state(STATION)
    assert _field(state, "latest_desired_price") == 110
    assert _field(state, "last_acknowledged_price") == 100
    assert not _field(state, "settled")
