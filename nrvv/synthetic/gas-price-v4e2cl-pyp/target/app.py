'''Price-update server (GASV4E2CL-18, -19, -20, -21).

At most one update is in flight per station. A new update is dispatched only when no update is
in flight and the desired price differs from the price of the most recent update sent to that
station. An acknowledgement clears the in-flight slot and runs the dispatch again, so the
station always ends up on the latest desired price.
'''
from dataclasses import dataclass


@dataclass
class _StationState:
    desired_price: object = None
    desired_version: int = 0
    last_sent_update_id: int = 0
    last_sent_price: object = None
    in_flight_update_id: object = None
    highest_acknowledged_id: int = 0


class Server:
    '''Keeps the desired price of each station and dispatches price updates to them.'''

    def __init__(self, send_price_update):
        self._send_price_update = send_price_update
        self._stations = {}

    def _state(self, station_id):
        if station_id not in self._stations:
            self._stations[station_id] = _StationState()
        return self._stations[station_id]

    def set_desired_price(self, station_id, price):
        '''GASV4E2CL-18: always accepted; sends nothing by itself beyond the dispatch rule.'''
        state = self._state(station_id)
        if price != state.desired_price:
            state.desired_price = price
            state.desired_version += 1
        self._dispatch(station_id)
        return True

    def acknowledgement_received(self, station_id, update_id):
        '''GASV4E2CL-20: an acknowledgement clears the in-flight slot, then dispatch runs.'''
        state = self._state(station_id)
        if state.in_flight_update_id == update_id:
            state.in_flight_update_id = None
        state.highest_acknowledged_id = max(state.highest_acknowledged_id, update_id)
        self._dispatch(station_id)

    def observe_station(self, station_id):
        '''GASV4E2CL-21: read-only view of what the server holds for a station.'''
        state = self._state(station_id)
        return {
            'desired_price': state.desired_price,
            'desired_version': state.desired_version,
            'last_sent_update_id': state.last_sent_update_id,
            'last_sent_price': state.last_sent_price,
            'in_flight_update_id': state.in_flight_update_id,
            'highest_acknowledged_id': state.highest_acknowledged_id,
        }

    def _dispatch(self, station_id):
        state = self._state(station_id)
        if state.desired_version == 0 or state.in_flight_update_id is not None:
            return
        if state.last_sent_update_id and state.desired_price == state.last_sent_price:
            return
        state.last_sent_update_id += 1
        state.last_sent_price = state.desired_price
        state.in_flight_update_id = state.last_sent_update_id
        self._send_price_update(station_id, state.last_sent_update_id, state.desired_price)
