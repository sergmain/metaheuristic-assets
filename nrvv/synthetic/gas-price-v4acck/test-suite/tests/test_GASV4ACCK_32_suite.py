'''GASV4ACCK-6: send an update to a station when its confirmed price is stale.'''

import app
from nrvv_env import Simulation, StationClient

SEEDS = (1, 7, 42)
P1 = 'P1'
P2 = 'P2'


def _new_server():
    '''The server side of app: its class if it has one, otherwise the module itself.'''
    operations = ('set_latest_price', 'tick', 'acknowledgement_received')
    classes = [v for v in vars(app).values()
               if isinstance(v, type) and v.__module__ == app.__name__
               and all(callable(getattr(v, op, None)) for op in operations)]
    return classes[0]() if classes else app


def _sim(seed, station):
    '''Environment with one station client and no generated price changes, bound to a fresh server.'''
    sim = Simulation(seed, [])
    sim.stations[station] = StationClient(station)
    return sim, sim.bind(_new_server())


def _sends(sim, station):
    return [r for r in sim.sends if r.station == station]


def _acknowledge(sim, server, station, price):
    '''Set a price, trigger the send step, then run the environment until that update is acknowledged.'''
    server.set_latest_price(station, price)
    sim.step()
    sim.run_until_idle()


def test_sends_one_update_carrying_latest_price_when_confirmed_price_is_stale():
    for seed in SEEDS:
        station = f'stale-{seed}'
        sim, server = _sim(seed, station)
        _acknowledge(sim, server, station, P1)
        acked = _sends(sim, station)
        assert [r.price for r in acked] == [P1], 'setup: P1 was not sent'
        assert acked[0].acknowledged_at is not None, 'setup: P1 was not acknowledged'

        baseline = len(_sends(sim, station))
        server.set_latest_price(station, P2)
        sim.step()
        new = _sends(sim, station)[baseline:]
        assert len(new) == 1
        assert new[0].price == P2


def test_sends_nothing_when_latest_price_equals_acknowledged_price():
    for seed in SEEDS:
        station = f'current-{seed}'
        sim, server = _sim(seed, station)
        _acknowledge(sim, server, station, P1)
        baseline = len(_sends(sim, station))
        assert baseline == 1, 'setup: P1 was not sent exactly once'

        server.set_latest_price(station, P1)
        sim.step()
        sim.run_until(sim.now + 60)
        assert len(_sends(sim, station)) == baseline


def test_no_duplicate_send_while_update_carrying_latest_price_is_in_flight():
    for seed in SEEDS:
        station = f'inflight-{seed}'
        sim, server = _sim(seed, station)
        _acknowledge(sim, server, station, P1)
        baseline = len(_sends(sim, station))

        server.set_latest_price(station, P2)
        in_flight = [r for r in _sends(sim, station)[baseline:]
                     if r.price == P2 and r.acknowledged_at is None]
        assert len(in_flight) == 1, 'setup: no unacknowledged P2 update is in flight'

        before = len(_sends(sim, station))
        sim.step()
        assert len(_sends(sim, station)) == before

        sim.run_until_idle()
        assert len(_sends(sim, station)) == before
