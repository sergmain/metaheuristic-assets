import importlib
import random

import app
from nrvv_env import Simulation

STATION = 'S1'
OTHER = 'S2'
SEEDS = range(10)


def _fresh_app():
    return importlib.reload(app)


def _two_prices(seed):
    rng = random.Random(seed * 7919 + 1)
    p1 = rng.randint(1, 500)
    p2 = rng.randint(501, 1000)
    return p1, p2


def _sent_prices(sim, station):
    return [u.price for u in sim.sent_log if u.station == station]


def _run_quiet(sim):
    sim.run(max_steps=10000)
    assert sim.is_quiet(), 'simulation did not reach a quiet state'


def test_superseded_price_not_sent_and_newer_price_sent_once():
    for seed in SEEDS:
        p1, p2 = _two_prices(seed)
        sim = Simulation(_fresh_app(), seed, script=[(STATION, p1), (STATION, p2)])
        _run_quiet(sim)
        sent = _sent_prices(sim, STATION)
        assert p1 not in sent, 'seed %d: superseded price %r was sent: %r' % (seed, p1, sent)
        assert sent.count(p2) == 1, 'seed %d: expected exactly one send of %r, got %r' % (seed, p2, sent)


def test_superseded_price_not_sent_with_interleaved_traffic_on_other_station():
    for seed in SEEDS:
        p1, p2 = _two_prices(seed)
        script = [(OTHER, 7), (STATION, p1), (OTHER, 8), (STATION, p2)]
        sim = Simulation(_fresh_app(), seed, script=script)
        _run_quiet(sim)
        sent = _sent_prices(sim, STATION)
        assert p1 not in sent, 'seed %d: superseded price %r was sent: %r' % (seed, p1, sent)
        assert sent.count(p2) == 1, 'seed %d: expected exactly one send of %r, got %r' % (seed, p2, sent)
