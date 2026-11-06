'''Suite for GASV4E2CL-14: compare against the last sent price, not the last acknowledged one.'''
import app
from nrvv_env import (
    Simulation, Change, price_at_send_violations, repeat_violations,
    unsent_change_violations, message_form_violations,
)

SEEDS = (1, 2, 3, 4, 5)
STATION = 'S1'


def _server_factory(send_price_update):
    classes = [
        cls for name, cls in vars(app).items()
        if name[:1].isupper() and isinstance(cls, type) and hasattr(cls, 'set_desired_price')
    ]
    assert len(classes) == 1, f'expected one server class in app, found {len(classes)}'
    return classes[0](send_price_update)


def _simulation(seed):
    # duration=0: no scheduled central price changes, so the test controls every change
    return Simulation(seed, _server_factory, duration=0)


def _set_price(sim, station_id, value):
    result = sim.server.set_desired_price(station_id, value)
    sim.changes.append(Change(sim.now, station_id, value, result))


def _sent_prices(sim, station_id):
    return [s.price for s in sim.sends if s.station == station_id]


def _assert_clean(sim):
    assert not price_at_send_violations(sim)
    assert not repeat_violations(sim)
    assert not message_form_violations(sim)
    assert not unsent_change_violations(sim)


def test_round_trip_before_ack_sends_nothing():
    for seed in SEEDS:
        sim = _simulation(seed)
        _set_price(sim, STATION, '100')
        assert _sent_prices(sim, STATION) == ['100'], f'seed {seed}: initial update not sent'
        _set_price(sim, STATION, '101')
        _set_price(sim, STATION, '100')
        assert _sent_prices(sim, STATION) == ['100'], f'seed {seed}: redundant send before ack'
        sim.run_until_idle()
        assert len(sim.from_station) == 1, f'seed {seed}: in-flight update was not acknowledged'
        assert _sent_prices(sim, STATION) == ['100'], f'seed {seed}: send after ack with desired 100'
        assert sim.stations[STATION].displayed_price == '100', f'seed {seed}: station not converged'
        _assert_clean(sim)


def test_move_away_while_in_flight_sends_new_price_after_ack():
    for seed in SEEDS:
        sim = _simulation(seed)
        _set_price(sim, STATION, '100')
        _set_price(sim, STATION, '101')
        assert _sent_prices(sim, STATION) == ['100'], f'seed {seed}: sent while 100 in flight'
        sim.run_until_idle()
        assert _sent_prices(sim, STATION) == ['100', '101'], f'seed {seed}: 101 not sent after ack'
        assert sim.stations[STATION].displayed_price == '101', f'seed {seed}: station not converged'
        _assert_clean(sim)


def test_round_trip_then_move_sends_only_the_new_price():
    for seed in SEEDS:
        sim = _simulation(seed)
        _set_price(sim, STATION, '100')
        _set_price(sim, STATION, '101')
        _set_price(sim, STATION, '100')
        assert _sent_prices(sim, STATION) == ['100'], f'seed {seed}: redundant send before ack'
        _set_price(sim, STATION, '101')
        assert _sent_prices(sim, STATION) == ['100'], f'seed {seed}: sent while 100 in flight'
        sim.run_until_idle()
        assert _sent_prices(sim, STATION) == ['100', '101'], f'seed {seed}: wrong sends {_sent_prices(sim, STATION)}'
        assert sim.stations[STATION].displayed_price == '101', f'seed {seed}: station not converged'
        _assert_clean(sim)
