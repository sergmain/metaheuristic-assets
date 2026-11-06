'''Tests for GASV4E2CM-18: timeout-based retry with the current desired price.'''
import app
from nrvv_env import DMAX, Simulation

PERIOD = 2 * DMAX + 1
SEEDS = (1, 2, 3)


def _field(status, names, index):
    for name in names:
        if isinstance(status, dict) and name in status:
            return status[name]
        if hasattr(status, name):
            return getattr(status, name)
    if isinstance(status, (tuple, list)):
        return status[index]
    raise AssertionError(f'cannot read {names[0]} from {status!r}')


def _in_flight(sim, station):
    '''Returns (desired price, in-flight price, in-flight send time) of the station as the service reports it.'''
    status = sim.status(station)
    return (
        _field(status, ('desired_price', 'desired'), 0),
        _field(status, ('in_flight_price', 'in_flight'), 2),
        _field(status, ('in_flight_send_time', 'in_flight_sent_at', 'in_flight_time', 'in_flight_since'), 3),
    )


def _unreachable(station, seed):
    sim = Simulation(app, seed, stations=(station,), loss=0.0, outage=0.0)
    sim.stations[station].outages.append((0, 10 ** 9))
    return sim


def _send_update(sim, station, price):
    '''Quiet ticks, then one desired-price change. Returns (simulation time t, service time of the in-flight record).'''
    for _ in range(7):
        sim.tick()
    sim.set_desired_price(station, price)
    if not sim.sent:
        sim.tick()
    assert len(sim.sent) == 1, f'expected one update, got {len(sim.sent)}'
    entry = sim.sent[0]
    assert (entry['station'], entry['price']) == (station, price), entry
    _, in_flight_price, app_sent = _in_flight(sim, station)
    assert in_flight_price == price, f'in-flight price {in_flight_price!r} right after the send'
    return entry['time'], app_sent


def _tick_checked(sim, station, price, app_sent, until):
    '''Ticks until simulation time until. Every tick the record must stay in flight and nothing may be sent.'''
    sent_before = len(sim.sent)
    while sim.now < until:
        sim.tick()
        _, in_flight_price, when = _in_flight(sim, station)
        assert (in_flight_price, when) == (price, app_sent), f'tick {sim.now}: in-flight record is {(in_flight_price, when)}'
        assert len(sim.sent) == sent_before, f'tick {sim.now}: an update was sent while one was in flight'


def _assert_resent(sim, station, price, sim_time, app_time, sent_before):
    '''At the expiry tick the record was cleared and exactly one update with the price was sent.'''
    assert sim.now == sim_time, f'expiry at tick {sim.now}, expected {sim_time}'
    assert len(sim.sent) == sent_before + 1, f'{len(sim.sent) - sent_before} updates sent at expiry'
    entry = sim.sent[-1]
    assert (entry['time'], entry['station'], entry['price']) == (sim_time, station, price), entry
    _, in_flight_price, when = _in_flight(sim, station)
    assert (in_flight_price, when) == (price, app_time), f'record after expiry is {(in_flight_price, when)}'


def test_update_stays_in_flight_until_expiry_then_resent():
    for seed in SEEDS:
        station = f'GASV4E2CM-33-a-{seed}'
        sim = _unreachable(station, seed)
        sim_t, app_t = _send_update(sim, station, 42)
        _tick_checked(sim, station, 42, app_t, sim_t + PERIOD - 1)
        sent_before = len(sim.sent)
        sim.tick()
        _assert_resent(sim, station, 42, sim_t + PERIOD, app_t + PERIOD, sent_before)
        assert sim.stations[station].received == []


def test_expiry_resends_desired_price_current_at_expiry():
    for seed in SEEDS:
        station = f'GASV4E2CM-33-b-{seed}'
        sim = _unreachable(station, seed)
        sim_t, app_t = _send_update(sim, station, 42)
        _tick_checked(sim, station, 42, app_t, sim_t + 3)
        sent_before = len(sim.sent)
        sim.set_desired_price(station, 77)
        assert len(sim.sent) == sent_before, 'a price change sent an update while one was in flight'
        assert _in_flight(sim, station)[0] == 77
        _tick_checked(sim, station, 42, app_t, sim_t + PERIOD - 1)
        sent_before = len(sim.sent)
        sim.tick()
        _assert_resent(sim, station, 77, sim_t + PERIOD, app_t + PERIOD, sent_before)
        assert sim.stations[station].received == []


def test_unreachable_station_resends_every_period():
    for seed in SEEDS:
        station = f'GASV4E2CM-33-c-{seed}'
        sim = _unreachable(station, seed)
        sim_t, app_t = _send_update(sim, station, 42)
        sim_sent, app_sent = sim_t, app_t
        for _ in range(3):
            _tick_checked(sim, station, 42, app_sent, sim_sent + PERIOD - 1)
            sent_before = len(sim.sent)
            sim.tick()
            sim_sent += PERIOD
            app_sent += PERIOD
            _assert_resent(sim, station, 42, sim_sent, app_sent, sent_before)
        assert sim.stations[station].received == []
