"""Price-update service for the stations of the nrvv network.

Per station, at most one update is in flight. The in-flight update carries an absolute
price and a sequence number; it is retransmitted with the same number and price when its
timeout expires. An acknowledgement of the in-flight number makes its price the shown price,
and then the desired price is sent if it differs from the shown one.

- set_desired_price records the desired price. If nothing is in flight, a price that
  differs from the shown price is sent at once. If an update is in flight, the change is
  pending and is sent after that update is acknowledged. A desired price equal to the
  shown price means the in-flight update is no longer wanted, so the station reports idle.
- ack_received takes the acknowledgement of the in-flight sequence number; any other
  acknowledgement is a duplicate or stale and is ignored.
- tick retransmits expired in-flight updates. The timeout starts at BASE_TIMEOUT, doubles
  on each retransmission up to CAP_TIMEOUT, and returns to BASE_TIMEOUT on acknowledgement.

The outbound port send_price_update is installed by the environment. The environment
calls set_desired_price, ack_received and tick between ticks, so a send made by a call
that is not inside tick belongs to the tick after the last one seen.
"""

BASE_TIMEOUT = 8
CAP_TIMEOUT = 64

_stations = {}
_clock = 0
_port = None


class StationRecord:
    """The service's record for one station."""

    def __init__(self):
        self.desired = None
        self.shown = None
        self.seq = 0
        self.flight_seq = None
        self.flight_price = None
        self.deadline = None
        self.pending = False
        self.timeout = BASE_TIMEOUT


def _session():
    """Start from empty records whenever the environment binds a new outbound port.

    The port is bound once per run of the environment, so a new binding is a new run;
    records of an earlier run must not carry over into it.
    """
    global _port, _clock
    port = globals().get('send_price_update')
    if port is not _port:
        _port = port
        _stations.clear()
        _clock = 0


def _record(station):
    if station not in _stations:
        _stations[station] = StationRecord()
    return _stations[station]


def _send_new(station, rec):
    rec.seq += 1
    rec.flight_seq = rec.seq
    rec.flight_price = rec.desired
    rec.timeout = BASE_TIMEOUT
    rec.deadline = _clock + 1 + rec.timeout
    rec.pending = False
    send_price_update(station, rec.seq, rec.desired)


def set_desired_price(station, price):
    _session()
    rec = _record(station)
    rec.desired = price
    if rec.flight_seq is None:
        if price != rec.shown:
            _send_new(station, rec)
    elif price == rec.shown:
        rec.pending = False
    else:
        rec.pending = True
    return True


def ack_received(station, seq):
    _session()
    rec = _record(station)
    if rec.flight_seq is None or seq != rec.flight_seq:
        return
    rec.shown = rec.flight_price
    rec.flight_seq = None
    rec.flight_price = None
    rec.deadline = None
    rec.timeout = BASE_TIMEOUT
    if rec.desired != rec.shown:
        _send_new(station, rec)
    else:
        rec.pending = False


def tick(tick):
    global _clock
    _session()
    _clock = tick
    for station, rec in list(_stations.items()):
        if rec.flight_seq is not None and tick >= rec.deadline:
            rec.timeout = min(2 * rec.timeout, CAP_TIMEOUT)
            rec.deadline = tick + rec.timeout
            send_price_update(station, rec.flight_seq, rec.flight_price)


def query_station_state(station):
    _session()
    rec = _stations.get(station) or StationRecord()
    wanted = rec.flight_seq is not None and rec.desired != rec.shown
    return {
        'desired_price': rec.desired,
        'shown_price': rec.shown,
        'in_flight_seq': rec.flight_seq if wanted else None,
        'in_flight_price': rec.flight_price if wanted else None,
        'pending': rec.pending,
        'timeout': rec.timeout,
    }
