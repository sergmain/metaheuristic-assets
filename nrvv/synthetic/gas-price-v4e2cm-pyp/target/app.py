'''Central price service: per station, the desired price, the confirmed price and at most one update in flight.

Dispatch is evaluated on clock ticks, so a desired price superseded before a tick is never sent.
An in-flight update that is not acknowledged within TIMEOUT ticks expires, and the desired price
current at that moment is sent again.
'''
from dataclasses import dataclass

TIMEOUT = 11  # ticks; one more than the worst round trip (update delay up to 5, then acknowledgement delay up to 5)


@dataclass(frozen=True)
class StationStatus:
    '''Snapshot of one station's record; None means no value.'''
    desired_price: object = None
    confirmed_price: object = None
    in_flight_price: object = None
    in_flight_send_time: object = None


@dataclass
class _Record:
    desired_price: object = None
    confirmed_price: object = None
    in_flight_price: object = None
    in_flight_send_time: object = None


_records = {}  # station_id -> _Record
_send = None  # send port: send(station_id, price)
_clock = 0  # logical time, advanced by clock_tick


def connect_send_port(send):
    '''Hands the price update send port to the service and starts a fresh service state for it.'''
    global _send, _clock
    _send = send
    _records.clear()
    _clock = 0


def set_desired_price(station_id, price):
    '''Replaces the station's desired price. Always accepted; dispatch happens on the next tick.'''
    _records.setdefault(station_id, _Record()).desired_price = price
    return True


def get_station_status(station_id):
    '''Read-only view of the station's record.'''
    rec = _records.get(station_id, _Record())
    return StationStatus(rec.desired_price, rec.confirmed_price, rec.in_flight_price, rec.in_flight_send_time)


def receive_acknowledgement(station_id):
    '''The station acknowledged its in-flight update: that price is now confirmed.'''
    rec = _records.get(station_id)
    if rec is None or rec.in_flight_price is None:
        return
    rec.confirmed_price = rec.in_flight_price
    rec.in_flight_price = None
    rec.in_flight_send_time = None


def clock_tick():
    '''Advances logical time: expires timed-out in-flight updates, then dispatches for every station.'''
    global _clock
    _clock += 1
    for station_id, rec in _records.items():
        if rec.in_flight_price is not None and _clock - rec.in_flight_send_time >= TIMEOUT:
            rec.in_flight_price = None
            rec.in_flight_send_time = None
        _dispatch(station_id, rec)


def _dispatch(station_id, rec):
    '''Sends the desired price if nothing is in flight and the desired price differs from the confirmed one.'''
    if rec.in_flight_price is not None or rec.desired_price is None or rec.desired_price == rec.confirmed_price:
        return
    rec.in_flight_price = rec.desired_price
    rec.in_flight_send_time = _clock
    _send(station_id, rec.desired_price)
