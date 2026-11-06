'''GASV4ACCJ-32 (requirement GASV4ACCJ-16): after a send for a station at T0, the next send for that station is issued at T0 + 60 s and carries the latest desired price, whether the previous send was acknowledged or abandoned.'''
import heapq

import app
from nrvv_env import Simulation

STATION = 'S1'
T0 = 5
FIRST_PRICE = 100
EARLY_PRICE = 110
LATEST_PRICE = 120
SEEDS = (0, 1, 2, 3)


def _scripted(seed, loss_rate):
    '''Simulation whose price changes are exactly the ones scheduled here, with no outages.'''
    sim = Simulation(seed, app, station_ids=(STATION,), loss_rate=loss_rate)
    sim._heap = [entry for entry in sim._heap if entry[2] != 'change']
    heapq.heapify(sim._heap)
    sim.stations[STATION].unreachable = []
    changes = [(T0, FIRST_PRICE), (T0 + 10, EARLY_PRICE), (T0 + 45, LATEST_PRICE), (T0 + 59, LATEST_PRICE)]
    for when, price in changes:
        sim._push(when, 'change', (STATION, price))
    return sim


def _sends(sim):
    return [send for send in sim.sends if send.station_id == STATION]


def test_acknowledged_send_next_send_is_at_t0_plus_60_with_latest_price():
    for seed in SEEDS:
        sim = _scripted(seed, loss_rate=0.0)
        sim.advance_to(T0 + 59)
        first = _sends(sim)
        assert [s.sent_at for s in first] == [T0], 'seed %d: sends before T0+60 are %r' % (seed, [s.sent_at for s in first])
        assert first[0].outcome == 'delivered', 'seed %d: first send was not delivered' % seed
        assert any(ack.send_id == first[0].send_id for ack in sim.acks), 'seed %d: first send was not acknowledged' % seed

        sim.advance_to(T0 + 60)
        sends = _sends(sim)
        assert [s.sent_at for s in sends] == [T0, T0 + 60], 'seed %d: send times are %r' % (seed, [s.sent_at for s in sends])
        assert sends[1].price == LATEST_PRICE, 'seed %d: slot send carried %r' % (seed, sends[1].price)


def test_abandoned_send_next_send_is_at_t0_plus_60_with_latest_price():
    for seed in SEEDS:
        sim = _scripted(seed, loss_rate=1.0)
        sim.advance_to(T0 + 59)
        first = _sends(sim)
        assert [s.sent_at for s in first] == [T0], 'seed %d: sends before T0+60 are %r' % (seed, [s.sent_at for s in first])
        assert first[0].outcome == 'lost', 'seed %d: first send was not abandoned' % seed
        assert sim.acks == [], 'seed %d: an acknowledgement arrived for the abandoned send' % seed

        sim.advance_to(T0 + 60)
        sends = _sends(sim)
        assert [s.sent_at for s in sends] == [T0, T0 + 60], 'seed %d: send times are %r' % (seed, [s.sent_at for s in sends])
        assert sends[1].price == LATEST_PRICE, 'seed %d: slot send carried %r' % (seed, sends[1].price)
