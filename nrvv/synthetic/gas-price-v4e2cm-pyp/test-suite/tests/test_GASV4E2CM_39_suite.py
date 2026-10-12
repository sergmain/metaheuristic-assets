'''GASV4E2CM-39: a superseded desired price is never dispatched; the replacement price is.'''
import importlib

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)


def fresh_sim(seed, **kwargs):
    importlib.reload(app)
    return Simulation(app, seed, **kwargs)


def test_replaced_price_is_the_one_dispatched_by_the_tick():
    for seed in SEEDS:
        sim = fresh_sim(seed, loss=0.0, outage=0.0)
        sim.set_desired_price('S1', 'A')
        sim.set_desired_price('S1', 'B')
        sim.tick()
        dispatched = [(e['station'], e['price']) for e in sim.sent]
        assert dispatched == [('S1', 'B')], f'seed {seed}: {dispatched}'
        sim.quiesce()
        assert sim.last_delivered_price('S1') == 'B', f'seed {seed}'
        assert all(e['price'] != 'A' for e in sim.sent), f'seed {seed}'


def test_superseded_price_never_transmitted_under_loss_and_outages():
    for seed in SEEDS:
        sim = fresh_sim(seed)
        sim.set_desired_price('S1', 'A')
        sim.set_desired_price('S1', 'B')
        sim.tick()
        sim.quiesce(bound=500, idle_ticks=100)
        prices = [e['price'] for e in sim.sent_to('S1')]
        assert prices, f'seed {seed}: no update dispatched for S1'
        assert set(prices) == {'B'}, f'seed {seed}: {prices}'
        assert all(e['price'] != 'A' for e in sim.sent), f'seed {seed}'
