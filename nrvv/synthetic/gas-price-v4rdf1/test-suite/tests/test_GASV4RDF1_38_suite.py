'''Tests for GASV4RDF1-8: a price superseded before sending is not sent.'''

import app
from nrvv_env import Simulation


P1 = 17
P2 = 42
P0 = 8


def _make_server(send_update, send_pricing_notice):
    for name in ('make_server', 'create_server'):
        factory = getattr(app, name, None)
        if callable(factory):
            return factory(send_update, send_pricing_notice)
    for name in dir(app):
        obj = getattr(app, name)
        if name[:1].isupper() and isinstance(obj, type) and hasattr(obj, 'set_desired_price'):
            return obj(send_update, send_pricing_notice)
    raise AssertionError('app provides no server taking the send_update and send_pricing_notice ports')


def _sent_prices(sim, station):
    return [update.price for update in sim.sent if update.station == station]


def test_superseded_price_is_not_sent_when_newer_price_arrives_before_send():
    for seed in range(5):
        sim = Simulation(seed, _make_server, ['S1', 'S2'], script=[[]])
        sim.server.set_desired_price('S1', P1)
        sim.server.set_desired_price('S1', P2)
        sim.run(max_steps=10000)
        prices = _sent_prices(sim, 'S1')
        assert P1 not in prices, f'seed {seed}: superseded P1 was sent, sent prices {prices}'
        assert prices.count(P2) == 1, f'seed {seed}: expected exactly one P2 update, sent prices {prices}'


def test_superseded_price_is_not_sent_while_other_station_traffic_runs():
    for seed in range(5):
        sim = Simulation(seed, _make_server, ['S1', 'S2'], script=[[('S2', 5), ('S2', 6)]])
        sim.server.set_desired_price('S1', P1)
        sim.server.set_desired_price('S1', P2)
        sim.run(max_steps=10000)
        prices = _sent_prices(sim, 'S1')
        assert P1 not in prices, f'seed {seed}: superseded P1 was sent, sent prices {prices}'
        assert prices.count(P2) == 1, f'seed {seed}: expected exactly one P2 update, sent prices {prices}'


def test_superseded_price_is_not_sent_while_earlier_update_is_outstanding():
    for seed in range(5):
        sim = Simulation(seed, _make_server, ['S1'], script=[[]])
        sim.server.set_desired_price('S1', P0)
        for _ in range(10000):
            if sim.delivered_updates or not sim.step():
                break
        assert sim.delivered_updates, f'seed {seed}: earlier update P0 was never delivered to the station'
        sim.server.set_desired_price('S1', P1)
        sim.server.set_desired_price('S1', P2)
        sim.run(max_steps=10000)
        prices = _sent_prices(sim, 'S1')
        assert P1 not in prices, f'seed {seed}: superseded P1 was sent, sent prices {prices}'
        assert prices.count(P2) == 1, f'seed {seed}: expected exactly one P2 update, sent prices {prices}'
