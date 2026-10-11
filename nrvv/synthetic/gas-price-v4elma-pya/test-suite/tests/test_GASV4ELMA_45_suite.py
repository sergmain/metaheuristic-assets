import pytest
import app
from nrvv_env import Simulation

REQUIRED = ('set_desired_price', 'acknowledgement_received', 'reachability_changed', 'station_state')
SEEDS = (45, 46, 47)


def _construct_server(dispatch_update):
    for name in sorted(dir(app)):
        obj = getattr(app, name)
        if not isinstance(obj, type):
            continue
        if not any(word in name.lower() for word in ('server', 'service', 'tracker')):
            continue
        for args in ((dispatch_update,), ()):
            try:
                instance = obj(*args)
            except TypeError:
                continue
            if all(callable(getattr(instance, m, None)) for m in REQUIRED):
                return instance
    pytest.fail('app provides no server class with the required operations')


def _server_factory(dispatch_update):
    return _construct_server(dispatch_update)


def _not_confirming_report(server):
    for owner in (server, app):
        for name in dir(owner):
            norm = name.lower().replace('_', '')
            if name.startswith('_') or 'confirm' not in norm or 'latest' not in norm:
                continue
            fn = getattr(owner, name)
            if not callable(fn) or isinstance(fn, type):
                continue
            try:
                return fn()
            except TypeError:
                return fn(server)
    pytest.fail('app provides no not-confirming-latest-price report')


def _stations_in(report):
    stations = set()
    for item in report:
        if isinstance(item, str):
            stations.add(item)
        elif isinstance(item, dict):
            stations.add(item.get('stationId', item.get('station_id')))
        elif isinstance(item, tuple):
            stations.add(item[0])
        else:
            stations.add(getattr(item, 'stationId', None) or getattr(item, 'station_id', None))
    return stations


def _sequence_sent(sim, station, price):
    seqs = [d.sequence for d in sim.dispatches if d.station == station and d.price == price]
    assert seqs, f'no dispatch of {price} to {station}'
    return seqs[-1]


def test_not_confirming_report_includes_station_acking_older_price():
    for seed in SEEDS:
        sim = Simulation(seed, _server_factory, stop_time=0.0)
        server = sim.server
        stale = sim.station_ids[0]
        server.set_desired_price(stale, '2.40')
        server.set_desired_price(stale, '2.50')
        server.acknowledgement_received(stale, _sequence_sent(sim, stale, '2.40'), '2.40')
        report = _stations_in(_not_confirming_report(server))
        assert stale in report, f'seed {seed}: {stale} missing from not-confirming report'


def test_not_confirming_report_omits_station_acking_latest_price():
    for seed in SEEDS:
        sim = Simulation(seed, _server_factory, stop_time=0.0)
        server = sim.server
        stale, current = sim.station_ids[0], sim.station_ids[1]
        server.set_desired_price(stale, '2.40')
        server.set_desired_price(stale, '2.50')
        server.acknowledgement_received(stale, _sequence_sent(sim, stale, '2.40'), '2.40')
        server.set_desired_price(current, '2.50')
        server.acknowledgement_received(current, _sequence_sent(sim, current, '2.50'), '2.50')
        report = _stations_in(_not_confirming_report(server))
        assert stale in report, f'seed {seed}: {stale} missing from not-confirming report'
        assert current not in report, f'seed {seed}: {current} wrongly in not-confirming report'
