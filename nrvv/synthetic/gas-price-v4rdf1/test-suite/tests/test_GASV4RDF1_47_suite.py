from collections.abc import Mapping

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)


def _field(state, word, position):
    if isinstance(state, Mapping):
        for key, value in state.items():
            if word in str(key).lower():
                return value
    if isinstance(state, tuple) and not hasattr(state, '_fields'):
        return state[position]
    for name in dir(state):
        if word in name.lower() and not name.startswith('_'):
            value = getattr(state, name)
            if not callable(value):
                return value
    raise AssertionError('no %s field in %r' % (word, state))


def _drive_to_latest_ack(sim, station, price):
    while sim.last_ack_price(station) != price:
        if not sim.step():
            sim.stations[station].receive(price)
            assert sim.step()
            break
    return sim.ack_log[-1].step


def _desired_at(call_log, station, step):
    prices = [c.price for c in call_log if c.station == station and c.step < step]
    return prices[-1] if prices else None


def test_latest_price_ack_confirms_price_and_notifies_pricing_once():
    for seed in SEEDS:
        sim = Simulation(app, seed, script=[('S1', 500)])
        ack_step = _drive_to_latest_ack(sim, 'S1', 500)
        state = sim.query('S1')
        assert _field(state, 'confirm', 0) == 500
        assert _field(state, 'desire', 1) == 500
        notices = [n for n in sim.notices if n.arrival == ack_step]
        assert len(notices) == 1
        assert notices[0].station == 'S1'
        assert notices[0].price == 500


def test_older_price_ack_sends_no_notice():
    for seed in SEEDS:
        sim = Simulation(app, seed, script=[('S1', 300), ('S1', 500)])
        sim.run()
        assert sim.is_quiet()
        assert sim.desired['S1'] == 500
        before = len(sim.notices)
        sim.stations['S1'].receive(300)
        assert sim.step()
        assert sim.ack_log[-1].price == 300
        assert len(sim.notices) == before


def test_random_runs_notify_only_for_acks_showing_latest_price():
    total = 0
    for seed in SEEDS:
        sim = Simulation(app, seed, calls=12)
        sim.run()
        ack_steps = {a.step for a in sim.ack_log}
        for n in sim.notices:
            assert n.arrival in ack_steps
        for ack in sim.ack_log:
            at_step = [n for n in sim.notices if n.arrival == ack.step]
            if ack.price == _desired_at(sim.call_log, ack.station, ack.step):
                assert len(at_step) <= 1
            else:
                assert at_step == []
            for n in at_step:
                assert n.station == ack.station
                assert n.price == ack.price
        total += len(sim.notices)
    assert total > 0
