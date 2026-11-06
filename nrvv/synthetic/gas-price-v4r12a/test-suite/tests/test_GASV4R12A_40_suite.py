'''GASV4R12A-14: no update is sent to a station whose acknowledged price equals the desired price.'''
import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)
PRICE = 100
OTHER = 200
SETTLE_LIMIT = 50
WAIT_LIMIT = 200


def _new_sim(seed):
    sim = Simulation(seed, stations=('s1',), stop_tick=0, fault_window=(0, 0),
                     max_delay=2, loss=0.0, change_rate=0.0)
    sim.attach(lambda send: app.Server(send_update=send))
    return sim


def _acknowledge(sim, price):
    sim.source_schedule = {sim.now + 1: [('s1', price)]}
    sim.step()
    for _ in range(SETTLE_LIMIT):
        if sim.acks and sim.acks[-1].displayed == price:
            return
        sim.step()
    raise AssertionError('setup: station never acknowledged {!r}'.format(price))


def _in_flight_versions(status):
    if isinstance(status, dict):
        items = list(status.items())
    else:
        items = [(name, getattr(status, name)) for name in dir(status) if not name.startswith('_')]
    for name, value in items:
        if 'flight' in name and isinstance(value, (list, tuple, set, frozenset, dict)):
            return list(value)
    raise AssertionError('query_station_status result exposes no in-flight list')


def test_no_send_when_acknowledged_equals_desired_without_in_flight_update():
    for seed in SEEDS:
        sim = _new_sim(seed)
        _acknowledge(sim, PRICE)
        # The update carrying OTHER is lost, so it is never acknowledged and OTHER stays the last sent price.
        tick = sim.now + 1
        sim.fault_start, sim.fault_end, sim.loss = tick, tick + 1, 1.0
        sim.source_schedule = {tick: [('s1', OTHER)]}
        sim.step()
        assert sim.sends[-1].price == OTHER and sim.sends[-1].lost, 'setup: OTHER was not sent and lost'
        # Desired price returns to PRICE, which equals the acknowledged price.
        sim.source_schedule = {sim.now + 1: [('s1', PRICE)]}
        sim.step()
        assert sim.latest_desired()['s1'] == PRICE, 'setup: desired price is not PRICE'
        assert sim.acks[-1].displayed == PRICE, 'setup: acknowledged price is not PRICE'
        sent_before = len(sim.sends)
        # Wait until the server reports no in-flight update for the station.
        for _ in range(WAIT_LIMIT):
            if not _in_flight_versions(sim.queries[-1].result):
                break
            sim.step()
        else:
            raise AssertionError('server never cleared the in-flight update for s1')
        # Trigger the send decision once with nothing in flight.
        sim.step()
        assert len(sim.sends) == sent_before, 'seed {}: update sent to s1 although acknowledged equals desired'.format(seed)


def test_no_send_when_acknowledged_equals_desired_with_in_flight_update():
    for seed in SEEDS:
        sim = _new_sim(seed)
        _acknowledge(sim, PRICE)
        # Keep the station unreachable so the update carrying OTHER stays in flight.
        sim.set_reachable('s1', False)
        tick = sim.now + 1
        sim.source_schedule = {tick: [('s1', OTHER)]}
        sim.step()
        assert sim.sends[-1].price == OTHER and not sim.sends[-1].lost, 'setup: OTHER was not sent'
        assert any(u.price == OTHER for u in sim.in_flight_updates()), 'setup: OTHER is not in flight'
        # Desired price returns to PRICE, which equals the acknowledged price.
        sim.source_schedule = {sim.now + 1: [('s1', PRICE)]}
        sim.step()
        assert sim.latest_desired()['s1'] == PRICE, 'setup: desired price is not PRICE'
        assert sim.acks[-1].displayed == PRICE, 'setup: acknowledged price is not PRICE'
        sent_before = len(sim.sends)
        # Trigger the send decision once with the OTHER update still in flight.
        sim.step()
        assert len(sim.sends) == sent_before, 'seed {}: update sent to s1 although acknowledged equals desired'.format(seed)
