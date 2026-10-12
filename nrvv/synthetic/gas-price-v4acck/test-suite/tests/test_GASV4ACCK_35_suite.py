'''Verifies GASV4ACCK-12: an acknowledgement records the acknowledged update's price
as the last-acknowledged price and clears the outstanding update.'''

from collections.abc import Mapping

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5, 6)
STATION = 'S1'
ACKED_NAMES = ('last_acknowledged_price', 'last_acked_price', 'acknowledged_price', 'last_ack_price')
OUTSTANDING_NAMES = ('outstanding_price', 'outstanding_update', 'outstanding')


def _make_server():
    classes = [v for v in vars(app).values()
               if isinstance(v, type) and v.__module__ == app.__name__]
    if len(classes) == 1:
        try:
            return classes[0]()
        except TypeError:
            pass
    return app


def _bind(seed, stations):
    sim = Simulation(seed, stations, changes_per_station=(1, 1))
    server = sim.bind(_make_server())
    return sim, server


def _step_until(sim, done):
    for _ in range(sim.max_steps):
        if done():
            return
        sim.step()
    raise AssertionError('condition not reached')


def _field(view, names, index):
    if isinstance(view, Mapping):
        for name in names:
            if name in view:
                return view[name]
    for name in names:
        if hasattr(view, name):
            return getattr(view, name)
    return view[index]


def _acked_price(view):
    return _field(view, ACKED_NAMES, 1)


def _outstanding_price(view):
    return _field(view, OUTSTANDING_NAMES, 2)


def test_ack_records_sent_price_as_last_acknowledged():
    for seed in SEEDS:
        sim, server = _bind(seed, [STATION])
        p1 = sim.reference_final_prices[STATION]
        _step_until(sim, lambda: bool(sim.acknowledgements))
        assert len(sim.sends) == 1 and sim.sends[0].price == p1
        assert len(sim.acknowledgements) == 1
        view = server.get_station_view(STATION)
        assert _acked_price(view) == p1
        assert _outstanding_price(view) is None
        assert sim.unacknowledged_sends() == []


def test_acknowledged_price_and_no_outstanding_hold_after_run_to_end():
    for seed in SEEDS:
        sim, server = _bind(seed, [STATION])
        p1 = sim.reference_final_prices[STATION]
        sim.run_to_end()
        assert len(sim.sends) == 1 and len(sim.acknowledgements) == 1
        view = server.get_station_view(STATION)
        assert _acked_price(view) == p1
        assert _outstanding_price(view) is None
        assert sim.unacknowledged_sends() == []


def test_each_station_records_its_own_sent_price():
    stations = ['S1', 'S2', 'S3']
    for seed in SEEDS:
        sim, server = _bind(seed, stations)
        sim.run_to_end()
        for station in stations:
            sends = [r for r in sim.sends if r.station == station]
            assert len(sends) == 1
            view = server.get_station_view(station)
            assert _acked_price(view) == sends[0].price == sim.reference_final_prices[station]
            assert _outstanding_price(view) is None
