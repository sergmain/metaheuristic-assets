"""Server side of the desired-price update service.

Each station has a desired price (overwritten by every change), a held price (the
last price the station acknowledged) and at most one outstanding send. A send is
due when the desired price differs from the held price, nothing is outstanding,
and at least 60 seconds have passed since the previous send. An unacknowledged
send is abandoned 30 seconds after it was made.

The server has no clock of its own. It learns the simulated time only from
simulated_time_wake_up, so it asks for a wake-up at once after each send, to learn
the exact time of that send, and at each instant a send becomes due or abandoned.
"""

import math
from dataclasses import dataclass
from typing import Optional

SEND_SPACING = 60.0
ABANDON_AFTER = 30.0

# Ports set by the environment when it connects; None until then.
send_price_update = None
request_wake_up = None


@dataclass
class Send:
    send_id: object
    price: int
    sent_at: Optional[float] = None  # None until a wake-up reports the time of the send


@dataclass
class StationStatus:
    station: object
    desired_price: Optional[int]
    held_price: Optional[int]
    outstanding_send: Optional[Send]
    last_send_time: Optional[float]


class _Station:
    def __init__(self):
        self.desired = None
        self.held = None
        self.last = None         # most recent send, outstanding or not
        self.outstanding = None  # the send awaiting acknowledgement or abandonment


class _Session:
    """Server state for one connection to the environment.

    The state belongs to the connection: when the environment connects again, it is
    a new simulation with its clock back at zero, so the server starts from nothing.
    """

    def __init__(self, owner):
        self.owner = owner
        self.now = None  # latest simulated time the server was told
        self.next_send_id = 1
        self.stations = {}
        self.wake_ups = set()  # times already asked for, so each is requested once

    def station(self, name):
        if name not in self.stations:
            self.stations[name] = _Station()
        return self.stations[name]

    def want_wake_up(self, at_time):
        if at_time not in self.wake_ups:
            self.wake_ups.add(at_time)
            request_wake_up(at_time)

    def set_desired(self, name, price):
        self.station(name).desired = price
        self.decide(name)

    def acknowledged(self, name, send_id):
        st = self.station(name)
        if st.outstanding is None or st.outstanding.send_id != send_id:
            return  # repeated or unknown acknowledgement
        st.held = st.outstanding.price
        st.outstanding = None
        self.decide(name)

    def wake(self, now):
        self.now = now
        for st in self.stations.values():
            if st.last is not None and st.last.sent_at is None:
                st.last.sent_at = now
                if st.outstanding is st.last:
                    self.want_wake_up(now + ABANDON_AFTER)
            if st.outstanding is not None and now >= st.outstanding.sent_at + ABANDON_AFTER:
                st.outstanding = None  # abandoned; the held price stays as it was
        for name in list(self.stations):
            self.decide(name)

    def decide(self, name):
        st = self.station(name)
        if st.desired is None or st.desired == st.held or st.outstanding is not None:
            return
        if st.last is not None:
            if st.last.sent_at is None:
                return  # the wake-up that reports the time of the last send decides again
            due_at = st.last.sent_at + SEND_SPACING
            while due_at - st.last.sent_at < SEND_SPACING:  # keep the gap >= 60 s after rounding
                due_at = math.nextafter(due_at, math.inf)
            if self.now is None or self.now < due_at:
                self.want_wake_up(due_at)
                return
        self._send(name, st)

    def _send(self, name, st):
        send = Send(self.next_send_id, st.desired)
        self.next_send_id += 1
        st.last = st.outstanding = send
        send_price_update(name, send.price, send.send_id)
        request_wake_up(0.0)  # a wake-up at once reports the time of this send


_session = None


def _current():
    global _session
    owner = getattr(send_price_update, "__self__", send_price_update)
    if _session is None or _session.owner is not owner:
        _session = _Session(owner)
    return _session


def set_desired_price(station, price):
    _current().set_desired(station, price)
    return True


def acknowledgement_received(station, send_id):
    _current().acknowledged(station, send_id)


def simulated_time_wake_up(now):
    _current().wake(now)


def query_station_status(station):
    st = _current().station(station)
    last_time = st.last.sent_at if st.last is not None else None
    return StationStatus(station, st.desired, st.held, st.outstanding, last_time)
