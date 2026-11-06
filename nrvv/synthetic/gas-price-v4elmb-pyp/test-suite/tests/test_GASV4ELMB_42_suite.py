"""GASV4ELMB-2: a new desired price is accepted while earlier updates are still unacknowledged."""
import app
from nrvv_env import Simulation

SEEDS = range(10)
REFUSAL_MARKERS = ('refus', 'reject', 'error', 'wait', 'deny', 'fail')


def _start(seed, stations):
    # Station names are unique per seed, so runs do not interfere through the shared app module.
    sim = Simulation(app, seed, stations=stations)
    # No scripted central changes and no outages: each test submits its prices itself.
    sim._script_by_tick = {}
    sim.outages = {s: [] for s in sim.station_ids}
    return sim


def _assert_accepted(result, station, price):
    assert result is not None and result is not False, (
        'set_desired_price(%r, %r) returned %r, not an accepted result' % (station, price, result))
    if isinstance(result, str):
        low = result.lower()
        for marker in REFUSAL_MARKERS:
            assert marker not in low, (
                'set_desired_price(%r, %r) returned a refusal: %r' % (station, price, result))


def test_second_price_accepted_while_first_update_unacknowledged():
    for seed in SEEDS:
        station = 'st%da' % seed
        sim = _start(seed, [station, 'st%db' % seed])
        sim.step()  # tick 1
        _assert_accepted(app.set_desired_price(station, 5), station, 5)
        # An update sent for price 5 reaches the station no earlier than tick 2, and its
        # acknowledgement no earlier than tick 3, so it is still unacknowledged at tick 2.
        sim.step()
        assert sim.server_state(station)['in_flight_seq'] is not None, (
            'seed %r: the update for price 5 is not in flight' % seed)
        _assert_accepted(app.set_desired_price(station, 9), station, 9)
        assert sim.server_state(station)['desired_price'] == 9, 'seed %r' % seed


def test_new_price_accepted_for_every_station_with_updates_in_flight():
    for seed in SEEDS:
        stations = ['st%da' % seed, 'st%db' % seed]
        sim = _start(seed, stations)
        sim.step()  # tick 1
        for s in stations:
            _assert_accepted(app.set_desired_price(s, 4), s, 4)
        sim.step()  # tick 2: the updates for price 4 are still unacknowledged
        for s in stations:
            assert sim.server_state(s)['in_flight_seq'] is not None, (
                'seed %r: the update for price 4 at %r is not in flight' % (seed, s))
            _assert_accepted(app.set_desired_price(s, 11), s, 11)
            assert sim.server_state(s)['desired_price'] == 11, 'seed %r station %r' % (seed, s)


def test_back_to_back_prices_all_accepted_before_any_acknowledgement():
    for seed in SEEDS:
        station = 'st%da' % seed
        sim = _start(seed, [station])
        sim.step()  # tick 1: no update has been acknowledged at this tick
        for price in (5, 9, 2):
            _assert_accepted(app.set_desired_price(station, price), station, price)
            assert sim.server_state(station)['desired_price'] == price, 'seed %r' % seed
