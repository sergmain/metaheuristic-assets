import random

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 5, 8)
MAX_SETTLE_TICKS = 2000


def _quiet_simulation(seed, stations):
    # Scripted central changes and outages are switched off so that each test makes every change itself.
    # The simulation still installs the send port on app and drives the ticks and acknowledgements.
    sim = Simulation(app, seed, stations=stations)
    sim._script_by_tick = {}
    sim.outages = {s: [] for s in sim.station_ids}
    return sim


def _change(sim, station, price):
    sim._central_change(sim.tick, station, price)
    return sim.changes[-1]


def _run_until_idle(sim, station):
    for _ in range(MAX_SETTLE_TICKS):
        if sim.server_state(station)['in_flight_seq'] is None:
            return
        sim.step()
    raise AssertionError('station %s still in flight after %d ticks (seed %r)' % (station, MAX_SETTLE_TICKS, sim.seed))


def _other_price(rng, first):
    return (first + rng.randint(1, 20)) % 21


def test_idle_station_change_sends_exactly_one_update_with_new_price():
    for seed in SEEDS:
        station = 'idle-%d' % seed
        sim = _quiet_simulation(seed, [station])
        price = random.Random(seed).randint(0, 20)
        sends_before = len(sim.sends)
        _change(sim, station, price)
        new_sends = sim.sends[sends_before:]
        assert len(new_sends) == 1, 'expected one update, got %d (seed %r)' % (len(new_sends), seed)
        send = new_sends[0]
        assert send.station == station
        assert send.seq == 1
        assert send.price == price
        assert send.desired == price
        assert send.retransmission is False


def test_idle_station_change_marks_station_in_flight():
    for seed in SEEDS:
        station = 'flight-%d' % seed
        sim = _quiet_simulation(seed, [station])
        price = random.Random(seed).randint(0, 20)
        _change(sim, station, price)
        sent = [s for s in sim.sends if s.station == station]
        assert len(sent) == 1
        view = sim.server_state(station)
        assert view['desired_price'] == price
        assert view['in_flight_seq'] == sent[0].seq
        assert view['in_flight_price'] == price


def test_idle_station_change_after_ack_uses_next_sequence_number():
    for seed in SEEDS:
        station = 'next-%d' % seed
        sim = _quiet_simulation(seed, [station])
        rng = random.Random(seed)
        first = rng.randint(0, 20)
        second = _other_price(rng, first)
        _change(sim, station, first)
        _run_until_idle(sim, station)
        last_seq = max(s.seq for s in sim.sends if s.station == station)
        sends_before = len(sim.sends)
        _change(sim, station, second)
        new_sends = sim.sends[sends_before:]
        assert len(new_sends) == 1, 'expected one update, got %d (seed %r)' % (len(new_sends), seed)
        assert new_sends[0].seq == last_seq + 1
        assert new_sends[0].price == second
        assert new_sends[0].retransmission is False
        view = sim.server_state(station)
        assert view['in_flight_seq'] == last_seq + 1
        assert view['in_flight_price'] == second


def test_in_flight_station_change_sends_nothing_and_sets_pending():
    for seed in SEEDS:
        station = 'busy-%d' % seed
        sim = _quiet_simulation(seed, [station])
        rng = random.Random(seed)
        first = rng.randint(0, 20)
        second = _other_price(rng, first)
        _change(sim, station, first)
        sends_before = len(sim.sends)
        _change(sim, station, second)
        assert len(sim.sends) == sends_before, 'update sent while in flight (seed %r)' % seed
        view = sim.server_state(station)
        assert view['pending']
        assert view['desired_price'] == second


def test_in_flight_station_change_keeps_original_update_in_flight():
    for seed in SEEDS:
        station = 'keep-%d' % seed
        sim = _quiet_simulation(seed, [station])
        rng = random.Random(seed)
        first = rng.randint(0, 20)
        second = _other_price(rng, first)
        _change(sim, station, first)
        before = sim.server_state(station)
        _change(sim, station, second)
        after = sim.server_state(station)
        assert after['in_flight_seq'] == before['in_flight_seq']
        assert after['in_flight_price'] == first


def test_idle_change_sends_while_other_station_is_in_flight():
    for seed in SEEDS:
        busy = 'other-busy-%d' % seed
        idle = 'other-idle-%d' % seed
        sim = _quiet_simulation(seed, [busy, idle])
        rng = random.Random(seed)
        _change(sim, busy, rng.randint(0, 20))
        sends_before = len(sim.sends)
        price = rng.randint(0, 20)
        _change(sim, idle, price)
        new_sends = sim.sends[sends_before:]
        assert len(new_sends) == 1, 'expected one update, got %d (seed %r)' % (len(new_sends), seed)
        assert new_sends[0].station == idle
        assert new_sends[0].seq == 1
        assert new_sends[0].price == price
