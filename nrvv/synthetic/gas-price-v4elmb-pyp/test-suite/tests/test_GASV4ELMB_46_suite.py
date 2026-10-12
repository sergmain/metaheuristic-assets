'''Requirement GASV4ELMB-9: no price update to a station already showing the desired price.'''
import random

import app
from nrvv_env import Simulation

STATION = 'S0'
SEEDS = range(1, 7)
CONVERGE_LIMIT = 3000
QUIET_TICKS = 80


def _new_sim(seed):
    sim = Simulation(app, seed, stations=['S0', 'S1', 'S2'])
    sim.script = []
    sim._script_by_tick = {}
    sim.outages = {s: [] for s in sim.station_ids}
    return sim


def _set_and_converge(sim, station, price):
    sim._central_change(sim.tick, station, price)
    for _ in range(CONVERGE_LIMIT):
        view = sim.server_state(station)
        if view['desired_price'] == price and view['shown_price'] == price and view['in_flight_seq'] is None:
            return view
        sim.step()
    raise AssertionError('station %s did not converge to %r (seed %r)' % (station, price, sim.seed))


def test_no_update_sent_when_station_already_shows_desired_price():
    for seed in SEEDS:
        sim = _new_sim(seed)
        price = random.Random(seed).randint(0, 20)
        _set_and_converge(sim, STATION, price)
        assert sim.stations[STATION].price == price, seed
        sends_before = len(sim.sends)
        deliveries_before = len(sim.deliveries[STATION])
        sim._central_change(sim.tick, STATION, price)
        for _ in range(QUIET_TICKS):
            sim.step()
        sent = [s for s in sim.sends[sends_before:] if s.station == STATION]
        assert len(sent) == 0, 'seed %r: %d update(s) sent to %s although it shows %r' % (seed, len(sent), STATION, price)
        assert len(sim.deliveries[STATION]) == deliveries_before, seed
        assert sim.server_state(STATION)['in_flight_seq'] is None, seed


def test_no_update_sent_when_latest_desired_price_is_the_shown_one():
    for seed in SEEDS:
        sim = _new_sim(seed)
        first = random.Random(seed).randint(0, 19)
        latest = first + 1
        _set_and_converge(sim, STATION, first)
        _set_and_converge(sim, STATION, latest)
        assert sim.stations[STATION].price == latest, seed
        sends_before = len(sim.sends)
        sim._central_change(sim.tick, STATION, latest)
        for _ in range(QUIET_TICKS):
            sim.step()
        sent = [s for s in sim.sends[sends_before:] if s.station == STATION]
        assert len(sent) == 0, 'seed %r: %d update(s) sent to %s although it shows %r' % (seed, len(sent), STATION, latest)


def test_control_price_change_does_produce_update():
    for seed in SEEDS:
        sim = _new_sim(seed)
        price = random.Random(seed).randint(0, 20)
        _set_and_converge(sim, STATION, price)
        sends_before = len(sim.sends)
        other = price + 1
        _set_and_converge(sim, STATION, other)
        sent = [s for s in sim.sends[sends_before:] if s.station == STATION]
        assert sent, seed
        assert any(s.price == other for s in sent), seed
