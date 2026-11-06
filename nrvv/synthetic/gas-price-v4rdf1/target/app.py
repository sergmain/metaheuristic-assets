'''Server side of the NRVV desired-price exchange (GASV4RDF1).

Per station the server keeps the confirmed price (the price of the last
acknowledgement), the desired price (last set by a central client) and the
outstanding updates, oldest first.

An update is sent only when the desired price differs from the confirmed price
and no outstanding update already carries it. An acknowledgement retires the
outstanding update carrying its price, or the oldest one if none carries it,
and sets the confirmed price. An acknowledgement that answers an outstanding
update and leaves a different desired price unconfirmed triggers one resend.
An acknowledgement showing the latest desired price is reported to the pricing
team at once.
'''

from typing import Any, NamedTuple

_send_update = None
_send_notice = None


class StationState(NamedTuple):
    confirmed: Any
    desired: Any
    outstanding: int


class UnacknowledgedStation(NamedTuple):
    station: str
    desired: Any
    confirmed: Any


class _StationRecord:

    def __init__(self):
        self.confirmed = None
        self.desired = None
        self.outstanding = []


_stations = {}


def bind_ports(send_update, send_notice):
    '''Attaches the outbound ports. Binding starts a new server session: the station state of an earlier binding is dropped.'''
    global _send_update, _send_notice
    _send_update = send_update
    _send_notice = send_notice
    _stations.clear()


def _record(station):
    if station not in _stations:
        _stations[station] = _StationRecord()
    return _stations[station]


def _send_if_needed(station, record):
    if record.desired is None or record.desired == record.confirmed:
        return
    if record.desired in record.outstanding:
        return
    record.outstanding.append(record.desired)
    _send_update(station, record.desired)


def _retire(record, price):
    # returns whether the acknowledgement answers an outstanding update carrying its price
    if price in record.outstanding:
        record.outstanding.remove(price)
        return True
    if record.outstanding:
        record.outstanding.pop(0)
    return False


def set_desired_price(station, price):
    record = _record(station)
    record.desired = price
    _send_if_needed(station, record)


def receive_acknowledgement(station, price):
    record = _record(station)
    answers_update = _retire(record, price)
    record.confirmed = price
    if price == record.desired:
        _send_notice(station, price)
    if answers_update:
        _send_if_needed(station, record)


def query_station_state(station):
    if station not in _stations:
        return StationState(None, None, 0)
    record = _stations[station]
    return StationState(record.confirmed, record.desired, len(record.outstanding))


def list_stations_not_acknowledging_latest_price():
    return [UnacknowledgedStation(station, record.desired, record.confirmed)
            for station, record in _stations.items()
            if record.desired is not None and record.confirmed != record.desired]
