'''Requirement GASV4E2CM-6: the last update to arrive at each station carries the latest desired price.'''
import importlib
import itertools
import random

import app
from nrvv_env import Simulation

SEEDS = range(30)
BOUND = 5000
IDLE_TICKS = 200  # longer than any service timeout, so every expiry has fired before the check
STATIONS = ('S1', 'S2', 'S3')


def _fresh_app():
    '''Reloads app so state from an earlier seeded run cannot leak into this one.'''
    return importlib.reload(app)


def _invert_inflight(sim, station_id):
    '''Reorders the in-transit updates of one station: the newest sent update gets the earliest arrival.'''
    in_transit = [update for update in sim._updates if update[2]['station'] == station_id]
    if len(in_transit) < 2:
        return
    dues = sorted(due for due, _, _ in in_transit)
    newest_first = sorted(in_transit, key=lambda update: -update[1])
    reassigned = [(due, seq, entry) for due, (_, seq, entry) in zip(dues, newest_first)]
    sim._updates = [update for update in sim._updates if update[2]['station'] != station_id] + reassigned


def _scramble_all(sim, stations):
    for station_id in stations:
        _invert_inflight(sim, station_id)


def _settle(sim, stations, scramble):
    '''Ticks until nothing is in flight and nothing was sent for IDLE_TICKS ticks.'''
    quiet = 0
    for _ in range(BOUND):
        if scramble:
            _scramble_all(sim, stations)
        sent_before = len(sim.sent)
        sim.tick()
        if sim.in_flight() or len(sim.sent) != sent_before:
            quiet = 0
        else:
            quiet += 1
            if quiet >= IDLE_TICKS:
                return
    raise AssertionError('service did not settle within %d ticks' % BOUND)


def _run(seed, stations=STATIONS, loss=0.2, outage=0.2, scramble=True, steps=60):
    sim = Simulation(_fresh_app(), seed, stations=stations, loss=loss, outage=outage)
    rng = random.Random(seed * 7919 + 1)
    prices = itertools.count(1)  # every price is unique, so a displayed superseded price is unambiguous
    for _ in range(steps):
        if rng.random() < 0.3:
            for _ in range(rng.randint(1, 4)):
                sim.set_desired_price(rng.choice(stations), next(prices))
        if scramble:
            _scramble_all(sim, stations)
        sim.tick()
    _settle(sim, stations, scramble)
    return sim


def _assert_latest_wins(sim, stations, seed):
    for station_id in stations:
        history = [price for _, sid, price in sim.desired_history if sid == station_id]
        if not history:
            continue
        latest, superseded = history[-1], set(history[:-1])
        assert sim.displayed(station_id) == latest, (seed, station_id, sim.displayed(station_id), latest)
        assert sim.last_delivered_price(station_id) == latest, (seed, station_id)
        assert sim.displayed(station_id) not in superseded, (seed, station_id)


def test_last_arrival_carries_latest_price_when_updates_are_scrambled():
    for seed in SEEDS:
        sim = _run(seed, loss=0, outage=0, scramble=True)
        _assert_latest_wins(sim, STATIONS, seed)


def test_last_arrival_carries_latest_price_with_losses_and_outages():
    for seed in SEEDS:
        sim = _run(seed, loss=0.2, outage=0.2, scramble=True)
        _assert_latest_wins(sim, STATIONS, seed)


def test_latest_price_wins_when_superseded_update_may_arrive_last():
    for seed in range(10):
        sim = Simulation(_fresh_app(), seed, stations=('S1',), loss=0, outage=0)
        sim.set_desired_price('S1', 10)
        sim.set_desired_price('S1', 20)
        _settle(sim, ('S1',), scramble=True)
        assert sim.displayed('S1') == 20, seed
        assert sim.displayed('S1') != 10, seed
