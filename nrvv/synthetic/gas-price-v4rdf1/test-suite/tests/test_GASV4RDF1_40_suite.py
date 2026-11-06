import importlib

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)


def _desired(state):
    if hasattr(state, '_asdict'):
        state = state._asdict()
    if isinstance(state, dict):
        for key, value in state.items():
            if 'desired' in str(key).lower():
                return value
        raise AssertionError('no desired price in state: %r' % (state,))
    return state[1]


def test_second_price_during_unacknowledged_update_overwrites_first():
    for seed in SEEDS:
        importlib.reload(app)
        sim = Simulation(app, seed, stations=('S1', 'S2'), script=[('S1', 100), ('S1', 200)])

        sim._issue_call()
        assert ('S1', 100) in sim.in_flight(), 'setting 100 did not send an update'
        sim._deliver_update()
        assert sim.pending_acks('S1') == 1, 'update 100 is not awaiting acknowledgement'
        sent_before = len(sim.sent_log)

        sim._issue_call()
        assert sim.pending_acks('S1') == 1
        assert _desired(sim.query('S1')) == 200

        sim.run(max_steps=10000)
        assert sim.is_quiet()
        assert _desired(sim.query('S1')) == 200

        later = [s for s in sim.sent_log[sent_before:] if s.station == 'S1']
        assert any(s.price == 200 for s in later), 'price 200 never reached the send decision'
        assert not any(s.price == 100 for s in later), 'earlier price 100 was retained'


def test_random_overwrites_keep_only_latest_desired_price():
    for seed in SEEDS:
        importlib.reload(app)
        sim = Simulation(app, seed, stations=('S1', 'S2'), calls=40, prices=(1, 1000))
        sim.run(max_steps=20000)
        assert sim.is_quiet()
        for name in ('S1', 'S2'):
            prices = [c.price for c in sim.call_log if c.station == name]
            if prices:
                assert _desired(sim.query(name)) == prices[-1]
