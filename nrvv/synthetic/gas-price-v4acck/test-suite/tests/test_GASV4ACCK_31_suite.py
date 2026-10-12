'''GASV4ACCK-2: once price changes for a station stop, the station settles on the latest price.'''

import importlib

import app
from nrvv_env import Simulation

STATIONS = ['pump-1', 'pump-2', 'pump-3', 'pump-4']
SEEDS = range(6)
SERVER_METHODS = ('set_latest_price', 'tick', 'get_station_view', 'acknowledgement_received')


def _new_server():
    '''Fresh server side: an app class carrying the operations, or the app module when they are module-level.'''
    for name in sorted(dir(app)):
        obj = getattr(app, name)
        if isinstance(obj, type) and name[:1].isupper() and all(hasattr(obj, m) for m in SERVER_METHODS):
            return obj()
    return importlib.reload(app)


def _latest_price(view):
    '''The latest price field of a GetStationView result.'''
    for name in ('latest_price', 'latest'):
        if isinstance(view, dict) and name in view:
            return view[name]
        if hasattr(view, name):
            return getattr(view, name)
    return view[0]


def _set_in_steps(sim, server, sequences):
    '''Set sequences[station][i] at logical time i + 1 for every station, then let the system settle.

    Generated changes are all at time 0 (window=0, one change per station), so they are processed
    before the explicit sequence starts and are overwritten by it.
    '''
    sim.run_until(0)
    for i in range(max(len(prices) for prices in sequences.values())):
        for station, prices in sequences.items():
            server.set_latest_price(station, prices[i])
        sim.step()
    sim.run_to_end()


def test_single_station_settles_on_last_set_price():
    server = _new_server()
    sim = Simulation(seed=1, stations=['S1'], window=0, changes_per_station=(1, 1))
    sim.bind(server)
    _set_in_steps(sim, server, {'S1': (1.50, 1.75, 1.60)})
    assert _latest_price(server.get_station_view('S1')) == 1.60
    assert sim.held_prices()['S1'] == 1.60


def test_each_station_settles_on_its_own_last_price():
    sequences = {
        'S1': (1.50, 1.75, 1.60),
        'S2': (2.50, 2.75, 2.60),
        'S3': (3.00, 1.25, 4.10),
        'S4': (5.00, 6.25, 0.75),
    }
    server = _new_server()
    sim = Simulation(seed=2, stations=list(sequences), window=0, changes_per_station=(1, 1))
    sim.bind(server)
    _set_in_steps(sim, server, sequences)
    for station, prices in sequences.items():
        assert _latest_price(server.get_station_view(station)) == prices[-1], station
        assert sim.held_prices()[station] == prices[-1], station


def test_final_price_equal_to_earlier_price_is_held():
    server = _new_server()
    sim = Simulation(seed=5, stations=['S1'], window=0, changes_per_station=(1, 1))
    sim.bind(server)
    _set_in_steps(sim, server, {'S1': (1.50, 1.75, 1.50)})
    assert _latest_price(server.get_station_view('S1')) == 1.50
    assert sim.held_prices()['S1'] == 1.50


def test_random_change_sequences_settle_on_latest_price():
    for seed in SEEDS:
        server = _new_server()
        sim = Simulation(seed, STATIONS)
        sim.bind(server)
        sim.run_to_end()
        held = sim.held_prices()
        for station in STATIONS:
            final = sim.reference_final_prices[station]
            assert _latest_price(server.get_station_view(station)) == final, (seed, station)
            assert held[station] == final, (seed, station)


def test_many_changes_per_station_settle_on_latest_price():
    for seed in SEEDS:
        server = _new_server()
        sim = Simulation(seed, STATIONS, changes_per_station=(5, 10))
        sim.bind(server)
        sim.run_to_end()
        held = sim.held_prices()
        for station in STATIONS:
            final = sim.reference_final_prices[station]
            assert _latest_price(server.get_station_view(station)) == final, (seed, station)
            assert held[station] == final, (seed, station)


def test_settled_price_stays_after_quiet_period():
    for seed in SEEDS:
        server = _new_server()
        sim = Simulation(seed, STATIONS)
        sim.bind(server)
        sim.run_to_end()
        before = {s: _latest_price(server.get_station_view(s)) for s in STATIONS}
        sim.run_until(sim.now + 300)
        for station in STATIONS:
            final = sim.reference_final_prices[station]
            assert before[station] == final, (seed, station)
            assert _latest_price(server.get_station_view(station)) == final, (seed, station)
            assert sim.held_prices()[station] == final, (seed, station)
