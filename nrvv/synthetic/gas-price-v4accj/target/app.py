"""Server side of the desired-price update service.

Each station has a desired price (overwritten by every change), a held price (the
price the station last acknowledged) and at most one outstanding send. A send is due
when the desired price differs from the held price, nothing is outstanding, and at
least SEND_SPACING seconds have passed since the previous send to that station. An
unacknowledged send is abandoned ABANDON_AFTER seconds after it was made; the held
price is left as it was.

The server has no clock of its own. The environment calls simulated_time_wakeup once
per simulated second, after that second's changes and acknowledgements that were due
before the wake-up, so every decision is taken at a wake-up that carries the true
time. Each acknowledgement that changes a held price is reported to the pricing team
at the next wake-up. An acknowledgement that the environment delivers after that
second's wake-up is reported at the following wake-up, one second late.

connect(ports) starts a new session; no state is carried over from the previous one.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

SEND_SPACING = 60
ABANDON_AFTER = 30


@dataclass
class Send:
    send_id: int
    price: int
    sent_at: int


@dataclass
class StationStatus:
    station: str
    desired_price: Optional[int]
    held_price: Optional[int]
    outstanding_send: Optional[Send]
    last_send_time: Optional[int]


class _Station:
    def __init__(self):
        self.desired: Optional[int] = None
        self.held: Optional[int] = None
        self.outstanding: Optional[Send] = None
        self.last_send_time: Optional[int] = None


class _Session:
    def __init__(self, ports):
        self.ports = ports
        self.now: Optional[int] = None
        self.next_send_id = 1
        self.stations: Dict[str, _Station] = {}
        self.newly_held: List[Tuple[str, int]] = []  # (station, price) awaiting notification

    def station(self, name: str) -> _Station:
        if name not in self.stations:
            self.stations[name] = _Station()
        return self.stations[name]

    def set_desired(self, name: str, price: int) -> None:
        self.station(name).desired = price

    def acknowledged(self, name: str, send_id: int) -> None:
        st = self.station(name)
        if st.outstanding is None or st.outstanding.send_id != send_id:
            return  # repeated or unknown acknowledgement
        st.held = st.outstanding.price
        st.outstanding = None
        self.newly_held.append((name, st.held))

    def wake(self, now: int) -> None:
        self.now = now
        for st in self.stations.values():
            if st.outstanding is not None and now - st.outstanding.sent_at >= ABANDON_AFTER:
                st.outstanding = None  # abandoned; the held price stays as it was
        for name, price in self.newly_held:
            self.ports.notify_pricing_team(name, price, now)
        self.newly_held.clear()
        for name, st in list(self.stations.items()):
            self._decide(name, st, now)

    def _decide(self, name: str, st: _Station, now: int) -> None:
        if st.desired is None or st.desired == st.held or st.outstanding is not None:
            return
        if st.last_send_time is not None and now - st.last_send_time < SEND_SPACING:
            return  # due at last_send_time + SEND_SPACING; the wake-up at that second decides
        send = Send(self.next_send_id, st.desired, now)
        self.next_send_id += 1
        st.outstanding = send
        st.last_send_time = now
        self.ports.send_price_update(name, send.price, send.send_id)

    def status(self, name: str) -> StationStatus:
        st = self.station(name)
        return StationStatus(name, st.desired, st.held, st.outstanding, st.last_send_time)


_session = _Session(None)


def connect(ports) -> None:
    global _session
    _session = _Session(ports)


def set_desired_price(station, price) -> bool:
    _session.set_desired(station, price)
    return True


def acknowledgement_received(station, send_id) -> None:
    _session.acknowledged(station, send_id)


def simulated_time_wakeup(now) -> None:
    _session.wake(now)


def query_station_status(station) -> StationStatus:
    return _session.status(station)
