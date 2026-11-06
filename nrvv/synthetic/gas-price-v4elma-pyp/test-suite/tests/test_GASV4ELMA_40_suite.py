"""GASV4ELMA-40: a new gas station starts with empty state; the desired-price slot is overwritten in place (GASV4ELMA-10)."""
import app
from nrvv_env import Simulation

SEEDS = (1, 7, 42)


def _server(dispatch):
    return app.Server(dispatch_update=dispatch)


def _sim(seed):
    return Simulation(seed=seed, server_factory=_server)


def _field(state, snake):
    camel = snake.split('_')[0] + ''.join(w.capitalize() for w in snake.split('_')[1:])
    for name in (snake, camel):
        if isinstance(state, dict) and name in state:
            return state[name]
        if hasattr(state, name):
            return getattr(state, name)
    raise AssertionError('StationState has no field %s' % snake)


def _is_empty(value):
    return value is None or value == ''


def test_new_station_reads_empty_initial_state():
    for seed in SEEDS:
        sim = _sim(seed)
        sid = sim.station_ids[0]
        state = sim.app.station_state(sid)
        assert _is_empty(_field(state, 'latest_desired'))
        assert _is_empty(_field(state, 'last_sent_price'))
        assert _is_empty(_field(state, 'last_sent_seq'))
        assert set(_field(state, 'outstanding')) == set()
        assert _field(state, 'reachable') is False
        assert sim.traffic('dispatch') == []


def test_second_desired_price_overwrites_first_in_single_slot():
    for seed in SEEDS:
        sim = _sim(seed)
        sid = sim.station_ids[0]
        assert sim.app.set_desired_price(sid, 1.50) == 'Accepted'
        assert sim.app.set_desired_price(sid, 1.75) == 'Accepted'
        state = sim.app.station_state(sid)
        assert _field(state, 'latest_desired') == 1.75
        assert _field(state, 'reachable') is False
        assert sim.traffic('dispatch') == []


def test_station_state_read_changes_nothing():
    for seed in SEEDS:
        sim = _sim(seed)
        sid = sim.station_ids[0]
        sim.app.set_desired_price(sid, 1.50)
        first = sim.app.station_state(sid)
        second = sim.app.station_state(sid)
        assert _field(first, 'latest_desired') == _field(second, 'latest_desired') == 1.50
        assert _field(second, 'reachable') is False
        assert sim.traffic('dispatch') == []


def test_first_dispatch_uses_sequence_one():
    for seed in SEEDS:
        sim = _sim(seed)
        sid = sim.station_ids[0]
        sim.app.reachability_changed(sid, True)
        sim.app.set_desired_price(sid, 1.50)
        dispatches = sim.traffic('dispatch')
        assert dispatches, 'no dispatch after station became reachable with a desired price'
        assert dispatches[0].seq == 1
        assert dispatches[0].price == 1.50
