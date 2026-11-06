'''GASV4RDF1-41: per-station state after two updates and two acknowledgements.

Drives app only through nrvv_env. Each test uses its own station name so that
any state app keeps across tests does not leak between them.
'''

import app
from nrvv_env import Simulation

STATION = 'G41-main'
STATION_SOLO = 'G41-solo'


def _state_items(state):
    if isinstance(state, dict):
        return list(state.values())
    if isinstance(state, (tuple, list)):
        return list(state)
    if hasattr(state, '_asdict'):
        return list(state._asdict().values())
    return list(vars(state).values())


def _state(sim, station):
    # the query returns confirmed price, desired price and outstanding count, in that order
    items = _state_items(sim.query(station))
    assert len(items) == 3, 'stored state must hold exactly three items, got %r' % (items,)
    return tuple(items)


def _acknowledge(sim, station, price):
    # the station produces one acknowledgement carrying this price; the environment delivers it
    sim.stations[station].acks.append(price)
    sim._deliver_ack()


def test_two_updates_then_two_acks_track_confirmed_desired_and_outstanding():
    sim = Simulation(app, seed=41, stations=(STATION,),
                     script=[(STATION, 'P1'), (STATION, 'P2')])
    sim._issue_call()  # desired price P1
    sim._issue_call()  # desired price P2, before any acknowledgement

    sent = [u.price for u in sim.sent_log if u.station == STATION]
    assert sent == ['P1', 'P2']

    confirmed, desired, outstanding = _state(sim, STATION)
    assert outstanding == 2

    _acknowledge(sim, STATION, 'A1')
    confirmed, desired, outstanding = _state(sim, STATION)
    assert confirmed == 'A1'
    assert outstanding == 1
    assert desired == 'P2'

    _acknowledge(sim, STATION, 'A2')
    confirmed, desired, outstanding = _state(sim, STATION)
    assert confirmed == 'A2'
    assert outstanding == 0
    assert desired == 'P2'


def test_station_state_consists_of_exactly_three_items():
    sim = Simulation(app, seed=41, stations=(STATION_SOLO,),
                     script=[(STATION_SOLO, 'P1')])
    sim._issue_call()  # desired price P1, one outstanding update

    items = _state(sim, STATION_SOLO)
    assert len(items) == 3
    assert 'P1' in items
    assert 1 in items
