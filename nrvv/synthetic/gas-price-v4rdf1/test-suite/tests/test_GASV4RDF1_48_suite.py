'''Verification of GASV4RDF1-9: a station's confirmed price is derived from its
acknowledgements processed in the order they are received.

Acknowledgements are produced by the simulated stations (Station.receive),
and delivered to app by the simulation, one per step, in receipt order.
'''

import app
from nrvv_env import Simulation

SEEDS = (0, 1, 2, 3, 4)


def _confirmed(state):
    '''Extract the confirmed price from the result of query_station_state.'''
    if isinstance(state, dict):
        for key, value in state.items():
            if 'confirm' in str(key).lower():
                return value
        raise AssertionError('no confirmed price in query result: %r' % (state,))
    if hasattr(state, 'confirmed'):
        return state.confirmed
    return state[0]


def test_confirmed_price_is_last_ack_not_first():
    for seed in SEEDS:
        sim = Simulation(app, seed, stations=('S1',), script=[])
        sim.stations['S1'].receive('1.00')
        sim.stations['S1'].receive('2.00')
        sim.run()
        assert [a.price for a in sim.ack_log] == ['1.00', '2.00']
        assert str(_confirmed(sim.query('S1'))) == '2.00'


def test_third_ack_updates_confirmed_price():
    for seed in SEEDS:
        sim = Simulation(app, seed, stations=('S1',), script=[])
        sim.stations['S1'].receive('1.00')
        sim.stations['S1'].receive('2.00')
        sim.run()
        assert str(_confirmed(sim.query('S1'))) == '2.00'
        sim.stations['S1'].receive('1.50')
        sim.run()
        assert [a.price for a in sim.ack_log] == ['1.00', '2.00', '1.50']
        assert str(_confirmed(sim.query('S1'))) == '1.50'


def test_confirmed_price_tracks_last_ack_per_station():
    for seed in SEEDS:
        sim = Simulation(app, seed, stations=('S1', 'S2'), script=[])
        sim.stations['S1'].receive('1.00')
        sim.stations['S1'].receive('2.00')
        sim.stations['S2'].receive('3.00')
        sim.stations['S2'].receive('4.00')
        sim.run()
        assert str(_confirmed(sim.query('S1'))) == '2.00'
        assert str(_confirmed(sim.query('S2'))) == '4.00'
        sim.stations['S2'].receive('3.50')
        sim.run()
        assert str(_confirmed(sim.query('S1'))) == '2.00'
        assert str(_confirmed(sim.query('S2'))) == '3.50'
