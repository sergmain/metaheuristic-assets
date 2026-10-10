'''Checks GASV4RDF1-9: a station's confirmed price comes from its acknowledgements in arrival order.'''

import random

import app
from nrvv_env import Simulation


SEEDS = (0, 1, 2, 3, 4)


def _server_factory():
    for name in ('make_server', 'Server', 'create_server'):
        factory = getattr(app, name, None)
        if factory is not None:
            return factory
    raise AssertionError('app provides no server factory')


def _simulation(seed, stations):
    return Simulation(seed, _server_factory(), stations, script=[])


def _ack(sim, station, price, update_id):
    sim.stations[station].receive(update_id, price)


def _confirmed_price(state):
    if isinstance(state, dict):
        matches = [value for key, value in state.items() if 'confirmed' in str(key).lower()]
        assert matches, f'no confirmed price in {state!r}'
        return matches[0]
    for name in ('confirmed_price', 'confirmed'):
        if hasattr(state, name):
            return getattr(state, name)
    if hasattr(state, '_fields'):
        matches = [field for field in state._fields if 'confirmed' in field.lower()]
        if matches:
            return getattr(state, matches[0])
    if isinstance(state, (tuple, list)):
        return state[0]
    raise AssertionError(f'cannot read confirmed price from {state!r}')


def test_confirmed_price_is_last_in_order_ack_not_first():
    for seed in SEEDS:
        sim = _simulation(seed, ['S1'])
        _ack(sim, 'S1', '1.00', 1)
        _ack(sim, 'S1', '2.00', 2)
        sim.run(max_steps=100)
        assert [ack.price for ack in sim.delivered_acks] == ['1.00', '2.00']
        assert str(_confirmed_price(sim.query('S1'))) == '2.00'


def test_third_ack_moves_confirmed_price_to_1_50():
    for seed in SEEDS:
        sim = _simulation(seed, ['S1'])
        _ack(sim, 'S1', '1.00', 1)
        _ack(sim, 'S1', '2.00', 2)
        sim.run(max_steps=100)
        assert str(_confirmed_price(sim.query('S1'))) == '2.00'
        _ack(sim, 'S1', '1.50', 3)
        sim.run(max_steps=100)
        assert [ack.price for ack in sim.delivered_acks] == ['1.00', '2.00', '1.50']
        assert str(_confirmed_price(sim.query('S1'))) == '1.50'


def test_other_station_acks_do_not_change_confirmed_price():
    for seed in SEEDS:
        sim = _simulation(seed, ['S1', 'S2'])
        rng = random.Random(seed)
        other_prices = ['9.00', '8.00', '7.00']
        rng.shuffle(other_prices)
        _ack(sim, 'S1', '1.00', 1)
        _ack(sim, 'S2', other_prices[0], 2)
        _ack(sim, 'S1', '2.00', 3)
        _ack(sim, 'S2', other_prices[1], 4)
        _ack(sim, 'S2', other_prices[2], 5)
        sim.run(max_steps=100)
        s1_acks = [ack.price for ack in sim.delivered_acks if ack.station == 'S1']
        assert s1_acks == ['1.00', '2.00']
        assert str(_confirmed_price(sim.query('S1'))) == '2.00'
        assert str(_confirmed_price(sim.query('S2'))) == other_prices[2]
