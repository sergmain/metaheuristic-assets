'''GASV4ACCK-14: redundant updates are suppressed by the single dispatch rule.'''

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)


def _field(view, names):
    for name in names:
        if isinstance(view, dict) and name in view:
            return view[name]
        if hasattr(view, name):
            return getattr(view, name)
    raise AssertionError('station view has none of the fields %r' % (names,))


def _latest(view):
    return _field(view, ('latest_price',))


def _acknowledged(view):
    return _field(view, ('last_acknowledged_price', 'last_acked_price', 'acknowledged_price'))


def _outstanding(view):
    value = _field(view, ('outstanding_price', 'outstanding_update_price', 'outstanding', 'pending_price'))
    if value is None:
        return None
    if isinstance(value, dict):
        return value['price']
    if hasattr(value, 'price'):
        return value.price
    return value


def _station(tag, seed):
    return 'GASV4ACCK-39-%s-%d' % (tag, seed)


def _simulation(station, seed, price):
    # One change at logical time 0 with a fixed price, so the only upstream input is known.
    return Simulation(seed, [station], window=0, changes_per_station=(1, 1),
                      price_range=(price, price))


def test_no_dispatch_when_latest_price_equals_last_acknowledged():
    for seed in SEEDS:
        station = _station('equal-ack', seed)
        sim = _simulation(station, seed, 100)
        sim.bind(app)
        sim.run_until_idle()
        assert sim.send_counts()[station] == 1
        assert sim.unacknowledged_sends() == []
        view = app.get_station_view(station)
        assert _latest(view) == 100
        assert _acknowledged(view) == 100
        assert _outstanding(view) is None

        app.set_latest_price(station, 100)
        assert len(sim.sends) == 1, 'latest price equal to acknowledged price was dispatched'
        sim.run_to_end()
        assert sim.send_counts()[station] == 1, 'redundant dispatch later in the run'
        view = app.get_station_view(station)
        assert _acknowledged(view) == 100
        assert _outstanding(view) is None


def test_outstanding_update_with_latest_price_is_not_redispatched():
    for seed in SEEDS:
        station = _station('outstanding', seed)
        sim = _simulation(station, seed, 120)
        sim.bind(app)
        sim.step()
        assert len(sim.sends) == 1 and sim.sends[0].acknowledged_at is None, \
            'setup: price 120 must be outstanding and unacknowledged'
        view = app.get_station_view(station)
        assert _outstanding(view) == 120

        app.set_latest_price(station, 120)
        assert len(sim.sends) == 1, 'outstanding update carrying 120 was re-dispatched'
        assert sim.sends[0].acknowledged_at is None
        view = app.get_station_view(station)
        assert _latest(view) == 120, 'target price not recorded as 120'
        assert _outstanding(view) == 120
        assert _acknowledged(view) != 120, 'station acknowledged before its acknowledgement arrived'

        sim.run_to_end()
        assert len(sim.sends) == 1, 'a pending update was created or sent later'
        view = app.get_station_view(station)
        assert _acknowledged(view) == 120
        assert _outstanding(view) is None
