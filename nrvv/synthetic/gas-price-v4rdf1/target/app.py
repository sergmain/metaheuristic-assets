'''Server side of the NRVV desired-price exchange (GASV4RDF1).

Per station the server keeps the confirmed price (from acknowledgements), the
desired price (from central clients) and the outstanding updates, oldest first.
An update is sent only when the desired price differs from the confirmed price
and no outstanding update already carries it. Acknowledgements retire the
oldest outstanding update in arrival order.
'''

import collections


class _StationState:

    def __init__(self):
        self.confirmed = None
        self.desired = None
        self.outstanding = collections.deque()


class Server:

    def __init__(self, send_update, send_pricing_notice):
        self._send_update = send_update
        self._send_pricing_notice = send_pricing_notice
        self._stations = {}

    def set_desired_price(self, station, price):
        state = self._state(station)
        state.desired = price
        self._send_if_needed(station, state)

    def receive_acknowledgement(self, station, price):
        state = self._state(station)
        if state.outstanding:
            state.outstanding.popleft()
        previous = state.confirmed
        state.confirmed = price
        if price == state.desired and price != previous:
            self._send_pricing_notice(station, price)
        self._send_if_needed(station, state)

    def query_station_state(self, station):
        state = self._state(station)
        return state.confirmed, state.desired, len(state.outstanding)

    def _state(self, station):
        if station not in self._stations:
            self._stations[station] = _StationState()
        return self._stations[station]

    def _send_if_needed(self, station, state):
        if state.desired is None or state.desired == state.confirmed:
            return
        if state.desired in state.outstanding:
            return
        self._send_update(station, state.desired)
        state.outstanding.append(state.desired)
