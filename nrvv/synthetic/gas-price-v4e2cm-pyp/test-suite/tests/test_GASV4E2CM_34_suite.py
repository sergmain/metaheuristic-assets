import random

import app
from nrvv_env import DMAX, Simulation

TICK_BOUND = 500
SEEDS = range(1, 6)
STATION = 'S1'


def _tick_until(sim, predicate):
    for _ in range(TICK_BOUND):
        if predicate():
            return True
        sim.tick()
    return predicate()


def _prices(seed):
    return random.Random(seed).sample(range(1, 100), 3)


def test_displayed_price_is_last_update_for_p1_p2_p3():
    for seed in SEEDS:
        sim = Simulation(app, seed, loss=0.0, outage=0.0)
        p1, p2, p3 = _prices(seed)

        sim.set_desired_price(STATION, p1)
        assert _tick_until(sim, lambda: sim.displayed(STATION) == p1), f'seed {seed}: P1 never displayed'

        sim.set_desired_price(STATION, p2)
        assert _tick_until(sim, lambda: sim.displayed(STATION) == p2), f'seed {seed}: P2 never displayed'
        assert sim.displayed(STATION) == p2
        assert sim.displayed(STATION) != p1
        assert sim.last_delivered_price(STATION) == p2

        sim.set_desired_price(STATION, p3)
        assert _tick_until(sim, lambda: sim.displayed(STATION) == p3), f'seed {seed}: P3 never displayed'
        assert sim.displayed(STATION) == p3
        assert sim.displayed(STATION) not in (p2, p1)
        assert sim.last_delivered_price(STATION) == p3


def test_displayed_price_stays_on_last_update_after_later_ticks():
    for seed in SEEDS:
        sim = Simulation(app, seed, loss=0.0, outage=0.0)
        p1, p2, p3 = _prices(seed)

        sim.set_desired_price(STATION, p1)
        assert _tick_until(sim, lambda: sim.displayed(STATION) == p1), f'seed {seed}: P1 never displayed'

        sim.set_desired_price(STATION, p2)
        assert _tick_until(sim, lambda: sim.displayed(STATION) == p2), f'seed {seed}: P2 never displayed'
        for _ in range(4 * DMAX):
            sim.tick()
            assert sim.displayed(STATION) == p2
            assert sim.displayed(STATION) != p1

        sim.set_desired_price(STATION, p3)
        assert _tick_until(sim, lambda: sim.displayed(STATION) == p3), f'seed {seed}: P3 never displayed'
        for _ in range(4 * DMAX):
            sim.tick()
            assert sim.displayed(STATION) == p3
            assert sim.displayed(STATION) not in (p2, p1)
