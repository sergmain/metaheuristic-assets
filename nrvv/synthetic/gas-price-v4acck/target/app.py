'''Server side of GASV4ACCK: one outstanding price update per station (stop-and-wait).

Operations: set_latest_price, tick, acknowledgement_received, get_station_view.
The outbound port send_price_update(station, price) is bound by the environment.
The operations are available both as module-level functions and on PriceServer.
'''

# Outbound port; the environment binds it (nrvv_env.Simulation.bind).
send_price_update = None

_server = None


def _empty_state():
    return {
        'latest_price': None,
        'latest_change_time': None,
        'last_acknowledged_price': None,
        'outstanding_price': None,
    }


class PriceServer:
    '''Per-station state and the single dispatch rule.'''

    def __init__(self, send_price_update=None):
        self.send_price_update = send_price_update
        self._now = None
        self._stations = {}

    def set_latest_price(self, station, price):
        state = self._stations.setdefault(station, _empty_state())
        state['latest_price'] = price
        state['latest_change_time'] = self._now
        self._dispatch(station)

    def tick(self, now):
        self._now = now
        for station in list(self._stations):
            self._dispatch(station)

    def acknowledgement_received(self, station):
        state = self._stations.get(station)
        if state is None or state['outstanding_price'] is None:
            raise RuntimeError(f'acknowledgement from {station!r} with no outstanding update')
        state['last_acknowledged_price'] = state['outstanding_price']
        state['outstanding_price'] = None
        self._dispatch(station)

    def get_station_view(self, station):
        state = self._stations.get(station, _empty_state())
        return {
            'latest_price': state['latest_price'],
            'last_acknowledged_price': state['last_acknowledged_price'],
            'outstanding_price': state['outstanding_price'],
            'latest_change_time': state['latest_change_time'],
        }

    def _dispatch(self, station):
        state = self._stations[station]
        if state['outstanding_price'] is not None:
            # stop-and-wait: the next update waits for the acknowledgement
            return
        latest = state['latest_price']
        if latest is None or latest == state['last_acknowledged_price']:
            return
        state['outstanding_price'] = latest
        self.send_price_update(station, latest)


def _current():
    '''The server for the current outbound port; a new bind starts a new server.'''
    global _server
    if _server is None or _server.send_price_update is not send_price_update:
        _server = PriceServer(send_price_update)
    return _server


def set_latest_price(station, price):
    _current().set_latest_price(station, price)


def tick(now):
    _current().tick(now)


def acknowledgement_received(station):
    _current().acknowledgement_received(station)


def get_station_view(station):
    return _current().get_station_view(station)
