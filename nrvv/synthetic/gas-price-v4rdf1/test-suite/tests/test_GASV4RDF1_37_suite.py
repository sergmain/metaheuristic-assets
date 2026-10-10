'''Tests for GASV4RDF1-6: price convergence uses only existing update and acknowledgement exchanges.'''

import app
from nrvv_env import Simulation


STATIONS = ['S1', 'S2']
MAX_STEPS = 10000


def _make_server(send_update, send_pricing_notice):
    server_classes = [value for value in vars(app).values()
                      if isinstance(value, type) and hasattr(value, 'set_desired_price')]
    if not server_classes:
        raise AssertionError('app defines no server class with set_desired_price')
    return server_classes[0](send_update, send_pricing_notice)


def test_station_displays_new_price_after_older_price():
    for seed in range(8):
        sim = Simulation(seed, _make_server, ['S1'], script=[[]])
        sim.server.set_desired_price('S1', 10)
        sim.run(max_steps=MAX_STEPS)
        assert sim.displayed('S1') == 10, 'seed %d: older price not displayed' % seed
        sim.server.set_desired_price('S1', 20)
        sim.run(max_steps=MAX_STEPS)
        shown = sim.displayed('S1')
        assert shown == 20, 'seed %d: station displays %r, expected 20' % (seed, shown)


def test_only_supported_exchanges_reach_station():
    for seed in range(8):
        sim = Simulation(seed, _make_server, STATIONS, script=[[('S1', 10), ('S1', 20)]])
        sim.run(max_steps=MAX_STEPS)
        set_prices = {(call.station, call.price) for call in sim.client_calls}
        for sent in sim.sent:
            assert sent.station in STATIONS
            assert (sent.station, sent.price) in set_prices
        sent_by_id = {sent.update_id: sent for sent in sim.sent}
        delivered_by_id = {}
        for delivered in sim.delivered_updates:
            assert delivered.update_id in sent_by_id
            delivered_by_id[delivered.update_id] = delivered
        for ack in sim.delivered_acks:
            assert ack.update_id in delivered_by_id
            delivered = delivered_by_id[ack.update_id]
            assert ack.station == delivered.station
            assert ack.price == delivered.price


def test_station_converges_to_latest_desired_price_with_many_clients():
    for seed in range(8):
        sim = Simulation(seed, _make_server, STATIONS, clients=3, calls=6)
        sim.run(max_steps=MAX_STEPS)
        for station in STATIONS:
            latest = sim.latest_desired(station)
            if latest is None:
                continue
            shown = sim.displayed(station)
            assert shown == latest, 'seed %d: %s displays %r, expected %r' % (seed, station, shown, latest)
