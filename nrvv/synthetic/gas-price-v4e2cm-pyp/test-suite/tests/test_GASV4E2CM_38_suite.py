'''GASV4E2CM-11: per-station state record kept by the service, observed through GetStationStatus.'''
import app
from nrvv_env import Simulation

NONE = 'none'
BOUND = 200


def _field(obj, names):
    for name in names:
        if isinstance(obj, dict):
            if name in obj:
                return obj[name]
        elif hasattr(obj, name):
            return getattr(obj, name)
    raise AssertionError(f'{obj!r} has none of the fields {names}')


def _value(raw):
    return None if raw is None or raw == NONE else raw


def _desired(status):
    return _value(_field(status, ('desired_price', 'desired')))


def _confirmed(status):
    return _value(_field(status, ('confirmed_price', 'confirmed')))


def _in_flight(status):
    '''Return (price, send_time) of the in-flight update; both None when there is none.'''
    raw = _field(status, ('in_flight_update', 'in_flight', 'inflight_update', 'inflight', 'in_flight_price'))
    if _value(raw) is None:
        return None, None
    if isinstance(raw, dict) or hasattr(raw, 'price'):
        price = _field(raw, ('price',))
        send_time = _field(raw, ('send_time', 'sent_at', 'sent_time'))
    else:
        price = raw
        send_time = _field(status, ('in_flight_send_time', 'send_time', 'in_flight_sent_at'))
    return _value(price), _value(send_time)


def _run_until_sent(sim, station_id):
    for _ in range(BOUND):
        if sim.sent_to(station_id):
            return
        sim.tick()
    raise AssertionError(f'no update was sent for {station_id}')


def _run_until_acked(sim, station_id):
    for _ in range(BOUND):
        if sim.acks_per_station()[station_id] >= 1:
            return
        sim.tick()
    raise AssertionError(f'no acknowledgement for {station_id}')


def test_fresh_station_record_reads_none_for_all_fields():
    for seed in (1, 2, 3):
        station_id = f'FRESH-{seed}'
        sim = Simulation(app, seed, stations=(station_id,), loss=0.0, outage=0.0)
        status = sim.status(station_id)
        assert _desired(status) is None
        assert _confirmed(status) is None
        assert _in_flight(status) == (None, None)


def test_accepted_desired_price_shows_desired_while_confirmed_stays_none():
    for seed in (4, 5, 6):
        station_id = f'DESIRED-{seed}'
        sim = Simulation(app, seed, stations=(station_id,), loss=0.0, outage=0.0)
        sim.set_desired_price(station_id, 'P1')
        status = sim.status(station_id)
        assert _desired(status) == 'P1'
        assert _confirmed(status) is None
        sim.quiesce()


def test_sent_update_is_in_flight_with_price_and_send_time():
    for seed in (7, 8, 9):
        station_id = f'SENT-{seed}'
        sim = Simulation(app, seed, stations=(station_id,), loss=0.0, outage=0.0)
        sim.set_desired_price(station_id, 'P1')
        _run_until_sent(sim, station_id)
        assert sim.sent_to(station_id)[0]['price'] == 'P1'
        price, send_time = _in_flight(sim.status(station_id))
        assert price == 'P1'
        assert send_time is not None
        sim.quiesce()


def test_second_update_is_refused_while_first_is_in_flight():
    for seed in (10, 11, 12):
        station_id = f'REFUSE-{seed}'
        sim = Simulation(app, seed, stations=(station_id,), loss=0.0, outage=0.0)
        sim.set_desired_price(station_id, 'P1')
        _run_until_sent(sim, station_id)
        sim.set_desired_price(station_id, 'P2')
        assert len(sim.sent_to(station_id)) == 1
        price, _ = _in_flight(sim.status(station_id))
        assert price == 'P1'
        sim.quiesce()


def test_acknowledgement_confirms_price_and_clears_in_flight():
    for seed in (13, 14, 15):
        station_id = f'ACK-{seed}'
        sim = Simulation(app, seed, stations=(station_id,), loss=0.0, outage=0.0)
        sim.set_desired_price(station_id, 'P1')
        _run_until_sent(sim, station_id)
        _run_until_acked(sim, station_id)
        status = sim.status(station_id)
        assert _confirmed(status) == 'P1'
        assert _in_flight(status) == (None, None)
        sim.quiesce()
