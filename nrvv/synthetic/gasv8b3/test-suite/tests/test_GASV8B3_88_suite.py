import pytest

import app
import nrvv_env

P1 = 10
P2 = 12
ST = "st-1"


def _field(state, *names):
    for n in names:
        if isinstance(state, dict) and n in state:
            return state[n]
        if hasattr(state, n):
            return getattr(state, n)
    raise AssertionError("state lacks any of %r: %r" % (names, state))


def _view(state):
    return (
        _field(state, "latest_desired_price", "latestDesiredPrice"),
        _field(state, "last_acknowledged_price", "lastAcknowledgedPrice"),
        _field(state, "settled"),
    )


def _state(station=ST):
    return _view(app.get_station_state(station))


def _setup(seed):
    sim = nrvv_env.Simulation(seed=seed, station_ids=(ST,))
    sim.connect(app)
    return sim


def _first_two_submits(sim):
    sim.submit(ST, P1)
    if len(sim.sends) != 1:
        pytest.skip("precondition not reached: first submit did not produce exactly one send")
    s1 = sim.sends[0]
    sim.submit(ST, P2)
    return s1


@pytest.mark.parametrize("seed", [0, 1, 7])
def test_superseded_ack_does_not_settle_and_triggers_followup(seed):
    sim = _setup(seed)
    s1 = _first_two_submits(sim)
    assert s1.price == P1
    assert len(sim.sends) == 1
    sim.deliver(s1.send_id)
    sim.deliver_ack()
    latest, _acked, settled = _state()
    assert latest == P2
    assert settled is False
    assert len(sim.sends) == 2
    s2 = sim.sends[1]
    assert s2.price == P2
    assert s2.send_id != s1.send_id


@pytest.mark.parametrize("seed", [0, 3])
def test_ack_of_followup_send_settles_on_latest(seed):
    sim = _setup(seed)
    s1 = _first_two_submits(sim)
    sim.deliver(s1.send_id)
    sim.deliver_ack()
    assert len(sim.sends) == 2
    s2 = sim.sends[1]
    sim.deliver(s2.send_id)
    sim.deliver_ack()
    latest, acked, settled = _state()
    assert settled is True
    assert acked == P2
    assert latest == P2
    assert len(sim.sends) == 2


def test_unmatched_ack_is_ignored_and_changes_no_state():
    sim = _setup(5)
    s1 = _first_two_submits(sim)
    before = _state()
    app.on_acknowledgement(ST, "no-such-send-id", P2)
    assert _state() == before
    assert len(sim.sends) == 1
    sim.deliver(s1.send_id)
    sim.deliver_ack()
    assert len(sim.sends) == 2
    s2 = sim.sends[1]
    mid = _state()
    # unknown identifier, out of arrival order (while s2 outstanding)
    app.on_acknowledgement(ST, "bogus-id", P2)
    assert _state() == mid
    assert mid[2] is False
    assert len(sim.sends) == 2
    sim.deliver(s2.send_id)
    sim.deliver_ack()
    assert _state()[2] is True
    assert _state()[1] == P2
    # unknown ack after settlement changes nothing either
    after = _state()
    app.on_acknowledgement(ST, "another-bogus", P1)
    assert _state() == after
    assert len(sim.sends) == 2
