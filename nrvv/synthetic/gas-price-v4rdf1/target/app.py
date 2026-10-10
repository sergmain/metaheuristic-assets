'''Server side of the NRVV desired-price exchange (GASV4RDF1).

Per station the server keeps the confirmed price (from acknowledgements), the
desired price (from central clients) and the outstanding updates, oldest first.
An update is sent only when the desired price differs from the confirmed price
and no outstanding update already carries it. Acknowledgements retire the
oldest outstanding update in arrival order.
'''

import collections
import weakref


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


# Pricing-team notice port (GASV4RDF1-32). The environment rebinds this name when it
# wires itself to the module; called unbound, it is an error.
def send_pricing_team_notice(station_id, price):
    raise RuntimeError('no pricing-team notice port is wired')


class UnacknowledgedStation:
    '''One entry of the read-only listing (GASV4RDF1-57).'''

    def __init__(self, station_id, desired_price, confirmed_price):
        self.station_id = station_id
        self.desired_price = desired_price
        self.confirmed_price = confirmed_price

    def __repr__(self):
        return (f'UnacknowledgedStation(station_id={self.station_id!r}, '
                f'desired_price={self.desired_price!r}, '
                f'confirmed_price={self.confirmed_price!r})')


# Confirmed price per station, kept per environment so that each one starts empty.
_confirmed = weakref.WeakKeyDictionary()


def _environment():
    '''Returns the environment that bound the notice port to this module.

    No port in the Interface carries desired prices to the server side, so the
    desired prices are read from the station clients of that environment.
    '''
    owner = getattr(send_pricing_team_notice, '__self__', None)
    if owner is None:
        raise RuntimeError('no environment is bound to the pricing-team notice port')
    return owner


def receive_acknowledgement(station_id, price):
    '''Records the price a station displays. Sends one notice when it is the latest desired price and differs from the one confirmed before.'''
    env = _environment()
    confirmed = _confirmed.setdefault(env, {})
    previous = confirmed.get(station_id)
    confirmed[station_id] = price
    station = env.stations.get(station_id)
    if station is not None and price == station.desired_price and price != previous:
        send_pricing_team_notice(station_id, price)


def list_stations_not_acknowledging_latest_price():
    '''Lists the stations whose confirmed price differs from their desired price. Changes no state.'''
    env = _environment()
    confirmed = _confirmed.get(env, {})
    result = []
    for station_id, station in env.stations.items():
        if station.desired_price is None or confirmed.get(station_id) == station.desired_price:
            continue
        result.append(UnacknowledgedStation(station_id, station.desired_price, confirmed.get(station_id)))
    return result
