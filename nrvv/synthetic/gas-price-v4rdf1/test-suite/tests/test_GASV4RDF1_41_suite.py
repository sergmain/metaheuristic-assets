'''Suite for GASV4RDF1-10: per-station state (desired, confirmed, outstanding updates).'''

from collections.abc import Mapping

import app
from nrvv_env import Simulation


SEEDS = (1, 2, 3)
STATION = 'S'


def _make_server(send_update, send_pricing_notice):
    '''Builds the server from the app class that offers the three server operations.'''
    classes = [obj for obj in vars(app).values()
               if isinstance(obj, type)
               and hasattr(obj, 'set_desired_price')
               and hasattr(obj, 'receive_acknowledgement')
               and hasattr(obj, 'query_station_state')]
    assert classes, 'app defines no server class with the required operations'
    return classes[0](send_update, send_pricing_notice)


def _start(seed):
    '''Sets desired price P1, then P2, for one station before any acknowledgement.'''
    sim = Simulation(seed, _make_server, [STATION], script=[])
    sim.server.set_desired_price(STATION, 'P1')
    sim.server.set_desired_price(STATION, 'P2')
    return sim


def _state(sim):
    '''Returns the station's stored state as (confirmed, desired, outstanding count).'''
    state = sim.query(STATION)
    values = tuple(state.values()) if isinstance(state, Mapping) else tuple(state)
    assert len(values) == 3, f'station state has {len(values)} items, expected 3'
    return values


def test_two_updates_sent_in_order_before_any_ack():
    for seed in SEEDS:
        sim = _start(seed)
        assert [(u.station, u.price) for u in sim.sent] == [(STATION, 'P1'), (STATION, 'P2')]


def test_first_ack_sets_confirmed_price_and_keeps_p2_outstanding():
    for seed in SEEDS:
        sim = _start(seed)
        sim.server.receive_acknowledgement(STATION, 'A1')
        assert _state(sim) == ('A1', 'P2', 1)


def test_second_ack_confirms_a2_and_empties_outstanding():
    for seed in SEEDS:
        sim = _start(seed)
        sim.server.receive_acknowledgement(STATION, 'A1')
        sim.server.receive_acknowledgement(STATION, 'A2')
        assert _state(sim) == ('A2', 'P2', 0)
        assert len(sim.sent) == 2
