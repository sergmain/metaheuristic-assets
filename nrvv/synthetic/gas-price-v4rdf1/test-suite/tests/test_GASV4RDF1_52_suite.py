import importlib

from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)
SCRIPT = [('S1', '100'), ('S1', '105'), ('S1', '110')]


def _fresh_app():
    import app
    return importlib.reload(app)


def _field(state, name, index):
    if isinstance(state, dict):
        for key, value in state.items():
            if name in str(key).lower():
                return value
        raise AssertionError('no %s in query result %r' % (name, state))
    if hasattr(state, name):
        return getattr(state, name)
    return state[index]


def _confirmed(state):
    return _field(state, 'confirmed', 0)


def _outstanding(state):
    return _field(state, 'outstanding', 2)


def test_each_ack_removes_oldest_update_and_sets_confirmed_price_in_arrival_order():
    for seed in SEEDS:
        app = _fresh_app()
        sim = Simulation(app, seed, stations=('S1',), script=SCRIPT)
        while sim.step():
            if sim.ack_log:
                state = sim.query('S1')
                # confirmed price is the price of the last acknowledgement handled
                assert _confirmed(state) == sim.last_ack_price('S1'), seed
                # each acknowledgement removes exactly one outstanding update
                assert _outstanding(state) == len(sim.sent_log) - len(sim.ack_log), seed
        assert sim.is_quiet(), seed
        assert len(sim.ack_log) > 0, seed
        assert len(sim.ack_log) == len(sent_or_none(sim)), seed
        state = sim.query('S1')
        assert _outstanding(state) == 0, seed
        assert _confirmed(state) == sim.last_ack_price('S1') == sim.ack_log[-1].price, seed


def sent_or_none(sim):
    return sim.sent_log
