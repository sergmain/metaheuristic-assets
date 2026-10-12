'''Suite for GASV4R12A-13: dispatch the latest desired price to each eligible station.

Each event (desired price change, acknowledgement, in-flight expiry, time tick) is
driven one at a time, and the updates it emits are checked against the latest
desired price and version set before the event.
'''
import random

import app
from nrvv_env import Simulation

STATIONS = ('s1', 's2', 's3')
SEEDS = (1, 2, 3, 4, 5)


def _new_run(seed):
    sim = Simulation(seed, stations=STATIONS, loss=0.0)
    server = sim.attach(lambda send: app.Server(send_update=send))
    return sim, server, {}


def _assert_event_updates(new_sends, latest):
    '''Each update names one station, carries its latest price and version, and at most one per station.'''
    per_station = {}
    for rec in new_sends:
        assert isinstance(rec.station, str), 'update must carry exactly one station id: {!r}'.format(rec.station)
        assert rec.station in latest, 'update for a station without a desired price: {}'.format(rec.station)
        per_station[rec.station] = per_station.get(rec.station, 0) + 1
        assert per_station[rec.station] == 1, 'more than one update for {} in one event'.format(rec.station)
        price, version = latest[rec.station]
        assert rec.price == price, 'update price {!r} != desired price {!r}'.format(rec.price, price)
        assert rec.version == version, 'update version {!r} != desired version {!r}'.format(rec.version, version)


def test_desired_price_change_emits_one_update_with_latest_price_and_version():
    for seed in SEEDS:
        sim, server, latest = _new_run(seed)
        rng = random.Random(seed)
        for _ in range(12):
            sid = rng.choice(STATIONS)
            price = rng.randint(1, 1000)
            fresh = sid not in latest
            mark = len(sim.sends)
            version = server.accept_desired_price(sid, price)
            latest[sid] = (price, version)
            new = sim.sends[mark:]
            _assert_event_updates(new, latest)
            if fresh:
                # first desired price for a station with nothing in flight must be dispatched once
                assert sum(1 for r in new if r.station == sid) == 1


def test_time_tick_emits_one_update_per_station_with_latest_price_and_version():
    for seed in SEEDS:
        sim, server, latest = _new_run(seed)
        rng = random.Random(seed)
        for sid in STATIONS:
            price = rng.randint(1, 1000)
            latest[sid] = (price, server.accept_desired_price(sid, price))
        for _ in range(40):
            mark = len(sim.sends)
            server.tick()
            _assert_event_updates(sim.sends[mark:], latest)


def test_acknowledgement_emits_one_update_per_station_with_latest_price_and_version():
    for seed in SEEDS:
        sim, server, latest = _new_run(seed)
        rng = random.Random(seed)
        for _ in range(3):
            for sid in STATIONS:
                price = rng.randint(1, 1000)
                latest[sid] = (price, server.accept_desired_price(sid, price))
            server.tick()
            for sid in rng.sample(STATIONS, len(STATIONS)):
                sent = [r for r in sim.sends if r.station == sid]
                if not sent:
                    continue
                last = sent[-1]
                displayed = sim.stations[sid].apply(last.price)
                mark = len(sim.sends)
                server.receive_acknowledgement(sid, last.version, displayed)
                _assert_event_updates(sim.sends[mark:], latest)


def test_in_flight_expiry_emits_resend_per_station_with_latest_price_and_version():
    for seed in SEEDS:
        sim, server, latest = _new_run(seed)
        rng = random.Random(seed)
        for sid in STATIONS:
            price = rng.randint(1, 1000)
            latest[sid] = (price, server.accept_desired_price(sid, price))
        # no acknowledgements are ever sent, so in-flight records can only leave by expiry
        for _ in range(200):
            mark = len(sim.sends)
            server.tick()
            _assert_event_updates(sim.sends[mark:], latest)
        for sid in STATIONS:
            assert sum(1 for r in sim.sends if r.station == sid) >= 2, \
                'expired in-flight update for {} was never re-dispatched'.format(sid)


def test_mixed_events_never_batch_stations_into_one_update():
    for seed in SEEDS:
        sim, server, latest = _new_run(seed)
        rng = random.Random(seed)
        for _ in range(60):
            mark = len(sim.sends)
            kind = rng.choice(('change', 'burst', 'tick', 'ack'))
            if kind == 'change':
                sid = rng.choice(STATIONS)
                price = rng.randint(1, 1000)
                latest[sid] = (price, server.accept_desired_price(sid, price))
            elif kind == 'burst':
                # several stations change in one event burst, then a tick
                for sid in STATIONS:
                    price = rng.randint(1, 1000)
                    latest[sid] = (price, server.accept_desired_price(sid, price))
                server.tick()
            elif kind == 'tick':
                server.tick()
            else:
                sid = rng.choice(STATIONS)
                sent = [r for r in sim.sends if r.station == sid]
                if sent:
                    last = sent[-1]
                    displayed = sim.stations[sid].apply(last.price)
                    server.receive_acknowledgement(sid, last.version, displayed)
            _assert_event_updates(sim.sends[mark:], latest)
