'''Tests for GASV4ACCK-8: a superseded pending price is never dispatched.'''
import random

import app
from nrvv_env import Simulation, StationClient

SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)


def _make_server():
    for name in sorted(dir(app)):
        obj = getattr(app, name)
        if isinstance(obj, type) and name[:1].isupper() and callable(getattr(obj, 'set_latest_price', None)):
            return obj()
    return app


def _prices(seed):
    rng = random.Random(seed)
    p1 = rng.randint(1, 20)
    p2 = rng.randint(21, 40)
    return p1, p2


def _scenario(seed, stations):
    # window=0 and no stations at construction: the environment generates no price changes,
    # so the test feeds every SetLatestPrice itself, before the first step.
    sim = Simulation(seed, [], window=0)
    for s in stations:
        sim.stations[s] = StationClient(s)
    server = _make_server()
    sim.bind(server)
    return sim, server


def test_superseded_price_dispatched_once_as_newest():
    for seed in SEEDS:
        p1, p2 = _prices(seed)
        sim, server = _scenario(seed, ['S'])
        server.set_latest_price('S', p1)
        server.set_latest_price('S', p2)
        sim.run_to_end()
        sent = [r for r in sim.sends if r.station == 'S']
        assert len(sent) == 1, (seed, [r.price for r in sent])
        assert sent[0].price == p2, (seed, sent[0].price, p2)
        assert sim.in_flight == 0


def test_superseded_price_never_sent_or_delivered():
    for seed in SEEDS:
        p1, p2 = _prices(seed)
        sim, server = _scenario(seed, ['S'])
        server.set_latest_price('S', p1)
        server.set_latest_price('S', p2)
        sim.run_to_end()
        assert all(r.price != p1 for r in sim.sends if r.station == 'S'), seed
        delivered = [price for _, station, price in sim.deliveries if station == 'S']
        assert p1 not in delivered, (seed, delivered)
        assert sim.stations['S'].held_price == p2, seed


def test_supersede_does_not_change_other_station_dispatch():
    for seed in SEEDS:
        p1, p2 = _prices(seed)
        q = p2 + 1
        sim, server = _scenario(seed, ['S', 'T'])
        server.set_latest_price('S', p1)
        server.set_latest_price('T', q)
        server.set_latest_price('S', p2)
        sim.run_to_end()
        counts = sim.send_counts()
        assert counts == {'S': 1, 'T': 1}, (seed, counts)
        t_sends = [r.price for r in sim.sends if r.station == 'T']
        assert t_sends == [q], (seed, t_sends)
        s_sends = [r.price for r in sim.sends if r.station == 'S']
        assert s_sends == [p2], (seed, s_sends)
