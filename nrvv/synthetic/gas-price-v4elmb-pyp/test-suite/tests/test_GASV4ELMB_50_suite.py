'''GASV4ELMB-4: the latest desired price of a station is the last price update delivered to it.'''
import app
from nrvv_env import Simulation, normalize_view

SEEDS = range(1, 31)
SPAN = 100000
_clock = [0]
_stations = [0]


def _run_station(seed, issued):
    '''Run one seeded simulation of a fresh station; issued is a list of (tick, price) set calls.

    Ticks are offset so the logical clock given to app never goes backwards across runs.
    '''
    _stations[0] += 1
    station = 'station-%d' % _stations[0]
    sim = Simulation(app, seed, stations=[station])
    base = _clock[0]
    _clock[0] += SPAN
    sim.tick = base
    sim.script = [(base + tick, station, price) for tick, price in issued]
    sim._script_by_tick = {}
    for tick, s, price in sim.script:
        sim._script_by_tick.setdefault(tick, []).append((s, price))
    sim.last_change_tick = max(tick for tick, _, _ in sim.script)
    sim.outages = {station: []}
    sim.run(max_ticks=base + SPAN - 1)
    return station, sim


def _check_latest_is_last_delivered(issued):
    for seed in SEEDS:
        station, sim = _run_station(seed, issued)
        delivered = sim.deliveries[station]
        assert delivered, 'seed %d: no update reached the station' % seed
        last = delivered[-1].price
        view = normalize_view(app.query_station_state(station))
        assert view['desired_price'] == last, 'seed %d: query returned %r, last delivered %r' % (seed, view['desired_price'], last)


def test_latest_desired_price_is_last_delivered_update_issued_1_50_1_60_1_70():
    _check_latest_is_last_delivered([(1, '1.50'), (2, '1.60'), (3, '1.70')])


def test_latest_desired_price_is_last_delivered_update_issued_1_70_1_60_1_50():
    _check_latest_is_last_delivered([(1, '1.70'), (2, '1.60'), (3, '1.50')])
