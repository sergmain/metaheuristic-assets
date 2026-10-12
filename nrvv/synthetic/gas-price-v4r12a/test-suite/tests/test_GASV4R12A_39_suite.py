'''Suite for GASV4R12A-10: the latest acknowledged price of a station is the price
carried by the most recently received acknowledgement from that station.
'''
import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3)


def _new_sim(seed):
    # No source changes, no loss, no fault window: only the test drives the server.
    sim = Simulation(seed, stations=('s1', 's2'), stop_tick=5, fault_window=(0, 0),
                     change_rate=0.0, loss=0.0, max_delay=1)
    sim.attach(lambda send: app.Server(send_update=send))
    return sim


def _send_for(sim, station, price, max_ticks=10):
    '''Accept a desired price, tick until the server sends it, and return the sent version.'''
    before = len(sim.sends)
    sim.server.accept_desired_price(station, price)
    for _ in range(max_ticks):
        sim.server.tick()
        for rec in sim.sends[before:]:
            if rec.station == station and rec.price == price:
                return rec.version
    raise AssertionError('no update sent for {} at price {!r}'.format(station, price))


def _latest_acknowledged_price(sim, station):
    status = sim.server.query_station_status(station)
    for name in ('latest_acknowledged_price', 'latest_acked_price', 'acknowledged_price',
                 'latest_ack_price', 'confirmed_price'):
        if isinstance(status, dict) and name in status:
            return status[name]
        if hasattr(status, name):
            return getattr(status, name)
    raise AssertionError('status exposes no latest acknowledged price: {!r}'.format(status))


def test_latest_acknowledged_price_is_last_received_when_price_rises():
    for seed in SEEDS:
        sim = _new_sim(seed)
        server = sim.server
        first = _send_for(sim, 's1', '100')
        server.receive_acknowledgement('s1', first, '100')
        second = _send_for(sim, 's1', '120')
        server.receive_acknowledgement('s1', second, '120')
        latest = _latest_acknowledged_price(sim, 's1')
        assert latest == '120', (
            'seed {}: expected latest acknowledged price 120 after acks 100 then 120, got {!r}'
            .format(seed, latest))
        assert latest != '100', 'seed {}: stale acknowledged price 100 returned'.format(seed)


def test_latest_acknowledged_price_is_last_received_when_price_falls():
    for seed in SEEDS:
        sim = _new_sim(seed)
        server = sim.server
        first = _send_for(sim, 's2', '120')
        server.receive_acknowledgement('s2', first, '120')
        second = _send_for(sim, 's2', '100')
        server.receive_acknowledgement('s2', second, '100')
        latest = _latest_acknowledged_price(sim, 's2')
        assert latest == '100', (
            'seed {}: expected latest acknowledged price 100 after acks 120 then 100, got {!r}'
            .format(seed, latest))
