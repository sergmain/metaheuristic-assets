'''GASV4ACCJ-53: one pricing-team notification per acknowledgement that holds a new price, due within 60 s.'''
from collections import Counter

import app
import nrvv_env

SEEDS = (1, 2, 3, 4, 5, 6)
DEADLINE_SECONDS = 60


def _server_factory(ports):
    if hasattr(app, 'set_desired_price'):
        connect = getattr(app, 'connect', None)
        if connect is not None:
            connect(ports)
        return app
    server_class = next(
        obj for name, obj in vars(app).items()
        if name[:1].isupper() and isinstance(obj, type) and hasattr(obj, 'set_desired_price'))
    return server_class(ports)


def _run(seed, **kwargs):
    sim = nrvv_env.Simulation(seed, _server_factory, **kwargs)
    sim.run_until_idle()
    return sim


def _held_acknowledgements(sim):
    '''(station_id, price, ack_time) for each acknowledgement that made a station hold a newly set desired price.'''
    held = []
    for station_id, station in sim.stations.items():
        for _change_time, price, converged_at in sim.convergence(station_id):
            if converged_at is None:
                continue
            delivery = next((d for d in station.deliveries if d.time == converged_at and d.price == price), None)
            if delivery is None:
                continue  # already held when the change arrived, so no acknowledgement made it hold
            ack_times = [a.time for a in sim.acks
                         if a.station_id == station_id and a.send_id == delivery.send_id and a.time >= delivery.time]
            assert ack_times, 'send %r was delivered but never acknowledged' % (delivery.send_id,)
            held.append((station_id, price, min(ack_times)))
    return held


def _issued_for(sim, key):
    station_id, price, ack_time = key
    return [n for n in sim.notifications if (n.station_id, n.price, n.ack_time) == key]


def _assert_one_notification_per_acknowledgement(sim):
    expected = Counter(_held_acknowledgements(sim))
    assert expected, 'no acknowledgement made a station hold a newly set price; nothing was checked'
    for key, count in expected.items():
        issued = _issued_for(sim, key)
        assert len(issued) == count, (
            'acknowledgement %r should give %d notification(s), got %d' % (key, count, len(issued)))


def _assert_notifications_within_deadline(sim):
    keys = set(_held_acknowledgements(sim))
    assert keys, 'no acknowledgement made a station hold a newly set price; nothing was checked'
    for key in keys:
        issued = _issued_for(sim, key)
        assert issued, 'acknowledgement %r produced no notification' % (key,)
        for n in issued:
            assert n.time <= key[2] + DEADLINE_SECONDS, (
                'notification for %r issued at %d, later than ack time %d plus %d s'
                % (key, n.time, key[2], DEADLINE_SECONDS))


def test_one_notification_per_held_price_acknowledgement():
    for seed in SEEDS:
        _assert_one_notification_per_acknowledgement(_run(seed))


def test_notification_issued_within_60_seconds_of_acknowledgement():
    for seed in SEEDS:
        _assert_notifications_within_deadline(_run(seed))


def test_one_notification_per_held_price_acknowledgement_under_pricing_faults():
    for seed in SEEDS[:3]:
        _assert_one_notification_per_acknowledgement(_run(seed, pricing_fault_rate=0.3))


def test_one_notification_per_held_price_acknowledgement_under_heavy_loss():
    for seed in SEEDS[:3]:
        _assert_one_notification_per_acknowledgement(_run(seed, loss_rate=0.5))


def test_notification_within_60_seconds_under_loss_and_pricing_faults():
    for seed in SEEDS[:3]:
        _assert_notifications_within_deadline(_run(seed, loss_rate=0.4, pricing_fault_rate=0.3))


def test_one_notification_per_held_price_acknowledgement_with_five_stations():
    stations = ('A', 'B', 'C', 'D', 'E')
    for seed in SEEDS[:3]:
        _assert_one_notification_per_acknowledgement(_run(seed, station_ids=stations))
