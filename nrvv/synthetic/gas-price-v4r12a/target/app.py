'''GASV4R12A server: per-station desired price register, update dispatch and
acknowledgement tracking.

Updates are sent only from tick() and receive_acknowledgement(), so a price that
is superseded before the next tick is never sent. Each station has at most one
in-flight record per desired version; a record that stays unacknowledged for
timeout_ticks is expired and the desired version is sent again.
'''
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

__all__ = ['Server', 'StationStatus']

DEFAULT_TIMEOUT_TICKS = 5


@dataclass
class StationStatus:
    station: Any
    desired_price: Any
    desired_version: int
    latest_acknowledged_price: Any
    up_to_date: bool
    in_flight_versions: List[int]


class _StationState:
    def __init__(self):
        self.desired_price = None
        self.desired_version = 0
        self.acknowledged_price = None
        self.acknowledged_version = None
        self.in_flight = {}  # version -> tick at which its update was sent


class Server:
    def __init__(self, send_update: Callable[[Any, Any, int], None],
                 timeout_ticks: int = DEFAULT_TIMEOUT_TICKS):
        if timeout_ticks < 1:
            raise ValueError('timeout_ticks must be at least 1')
        self._send_update = send_update
        self._timeout_ticks = timeout_ticks
        self._clock = 0
        self._stations: Dict[Any, _StationState] = {}

    def _state(self, station):
        if station not in self._stations:
            self._stations[station] = _StationState()
        return self._stations[station]

    def accept_desired_price(self, station, price) -> int:
        state = self._state(station)
        state.desired_price = price
        state.desired_version += 1
        return state.desired_version

    def query_station_status(self, station) -> StationStatus:
        state = self._state(station)
        return StationStatus(
            station=station,
            desired_price=state.desired_price,
            desired_version=state.desired_version,
            latest_acknowledged_price=state.acknowledged_price,
            up_to_date=bool(state.acknowledged_version == state.desired_version
                            and state.acknowledged_price == state.desired_price),
            in_flight_versions=sorted(state.in_flight),
        )

    def receive_acknowledgement(self, station, version, displayed_price):
        state = self._state(station)
        state.in_flight.pop(version, None)
        state.acknowledged_price = displayed_price
        state.acknowledged_version = version
        self._dispatch(station, state)

    def tick(self):
        self._clock += 1
        for state in self._stations.values():
            for version, sent_tick in list(state.in_flight.items()):
                if self._clock - sent_tick >= self._timeout_ticks:
                    del state.in_flight[version]
        for station, state in list(self._stations.items()):
            self._dispatch(station, state)

    def _dispatch(self, station, state):
        if state.desired_version == 0:
            return
        if state.acknowledged_price == state.desired_price:
            return
        if state.desired_version in state.in_flight:
            return
        state.in_flight[state.desired_version] = self._clock
        self._send_update(station, state.desired_price, state.desired_version)
