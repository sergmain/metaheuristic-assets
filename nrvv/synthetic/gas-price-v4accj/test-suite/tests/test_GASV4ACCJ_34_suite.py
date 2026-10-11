'''Verifies GASV4ACCJ-8: at most one price update per station in any 60-second period.'''
import random

import app
from nrvv_env import Simulation

PERIOD = 60
LATER_CHANGE_AT = 100
STATION = 'S1'
SEEDS = (0, 1, 2, 3, 4)


def _server(ports):
    if hasattr(app, 'connect'):
        app.connect(ports)
        return app
    return app.Server(ports)


def _scenario(seed):
    rng = random.Random(seed)
    times = sorted(rng.sample(range(PERIOD), 3))
    prices = rng.sample(range(50, 151), 3)
    later_price = max(prices) + 1
    sim = Simulation(seed, _server, station_ids=(STATION,), horizon=0, loss_rate=0.0)
    sim.stations[STATION].unreachable = []
    for when, price in zip(times, prices):
        sim._push(when, 'change', (STATION, price))
    sim._push(LATER_CHANGE_AT, 'change', (STATION, later_price))
    return sim, prices, later_price


def test_changes_within_one_period_send_one_update_with_latest_price():
    for seed in SEEDS:
        sim, prices, _ = _scenario(seed)
        sim.advance_to(PERIOD - 1)
        sent = [s for s in sim.sends if s.station_id == STATION and s.sent_at < PERIOD]
        assert len(sent) == 1, (seed, [(s.sent_at, s.price) for s in sent])
        assert sent[0].price == prices[-1], (seed, sent[0].price, prices)


def test_change_after_period_sends_exactly_one_more_update():
    for seed in SEEDS:
        sim, prices, later_price = _scenario(seed)
        sim.run_until_idle()
        sends = [s for s in sim.sends if s.station_id == STATION]
        assert len(sends) == 2, (seed, [(s.sent_at, s.price) for s in sends])
        assert sends[1].price == later_price, (seed, sends[1].price, later_price)
        assert sends[1].sent_at >= sends[0].sent_at + PERIOD, (seed, [(s.sent_at, s.price) for s in sends])


def test_sends_to_each_station_are_at_least_a_period_apart():
    for seed in (0, 1, 2):
        sim = Simulation(seed, _server, horizon=600)
        sim.run_until_idle()
        for sid in sim.stations:
            times = sorted(s.sent_at for s in sim.sends if s.station_id == sid)
            gaps = [b - a for a, b in zip(times, times[1:])]
            assert all(g >= PERIOD for g in gaps), (seed, sid, times)
