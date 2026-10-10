import app
from nrvv_env import Simulation

FIRST = 100
SECOND = 200


def _desired_of(state):
    if isinstance(state, dict):
        for key, value in state.items():
            if 'desired' in key:
                return value
        raise AssertionError('no desired price in state: %r' % (state,))
    if hasattr(state, 'desired'):
        return state.desired
    return state[1]


def _drive_to_second_call(seed):
    sim = Simulation(app, seed, script=[('S1', FIRST), ('S1', SECOND)])
    while len(sim.call_log) < 2:
        assert sim.step(), 'simulation stopped before the second call'
    return sim


def test_second_price_accepted_while_first_unacknowledged():
    exercised = 0
    for seed in range(40):
        sim = _drive_to_second_call(seed)
        second_step = sim.call_log[1].step
        acked = any(a.station == 'S1' and a.price == FIRST and a.step < second_step
                    for a in sim.ack_log)
        if acked:
            continue
        exercised += 1
        assert _desired_of(sim.query('S1')) == SECOND, 'seed %d' % seed
    assert exercised > 0


def test_every_new_price_accepted_immediately_under_random_traffic():
    for seed in range(20):
        sim = Simulation(app, seed, calls=30, prices=(1, 1000))
        while True:
            before = len(sim.call_log)
            if not sim.step():
                break
            if len(sim.call_log) > before:
                last = sim.call_log[-1]
                assert _desired_of(sim.query(last.station)) == last.price, 'seed %d' % seed
        assert len(sim.call_log) == 30, 'seed %d' % seed
