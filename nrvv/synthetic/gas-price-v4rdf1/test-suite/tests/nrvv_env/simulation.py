'''Simulated environment for the nrvv system under test.

Simulates the clients (central clients, stations, pricing team) and the transport between them and the server side. The server side is the module app, handed in by the test; this module never imports it.

Ports: the outbound ports send_update and send_notice are attached to app when the simulation is built. If app has bind_ports, it is called with send_update=... and send_notice=...; otherwise both are set as attributes on app.
'''

import random
from collections import deque, namedtuple

SentUpdate = namedtuple('SentUpdate', 'step station price desired')
Ack = namedtuple('Ack', 'step station price')
Call = namedtuple('Call', 'step station price')
Notice = namedtuple('Notice', 'arrival station price')


class Station:
    '''Simulated station: one displayed price; one acknowledgement per received update, in receipt order.'''

    def __init__(self, name):
        self.name = name
        self.displayed = None
        self.acks = deque()

    def receive(self, price):
        self.displayed = price
        self.acks.append(price)


class Simulation:
    def __init__(self, app, seed, stations=('S1', 'S2'), calls=10, script=None, prices=(1, 1000)):
        self.app = app
        self.seed = seed
        self.rng = random.Random(seed)
        self.stations = {name: Station(name) for name in stations}
        self.prices = prices
        self._script = deque(script) if script is not None else None
        self._remaining_calls = len(script) if script is not None else calls
        self.step_no = 0
        self.desired = {}
        self.call_log = []
        self.sent_log = []
        self.ack_log = []
        self.notices = []
        self._in_flight = []
        bind = getattr(app, 'bind_ports', None)
        if callable(bind):
            bind(send_update=self.send_update, send_notice=self.send_notice)
        else:
            app.send_update = self.send_update
            app.send_notice = self.send_notice

    def _require_station(self, station):
        if station not in self.stations:
            raise ValueError('unknown station: %r' % (station,))

    # outbound port of the server side
    def send_update(self, station, price):
        self._require_station(station)
        self._in_flight.append((station, price))
        self.sent_log.append(SentUpdate(self.step_no, station, price, self.desired.get(station)))

    # outbound port to the pricing team (recorder; arrival is the logical step of the call)
    def send_notice(self, station, price):
        self.notices.append(Notice(self.step_no, station, price))

    def step(self):
        kinds = []
        if self._remaining_calls > 0:
            kinds.append('call')
        if self._in_flight:
            kinds.append('update')
        if any(s.acks for s in self.stations.values()):
            kinds.append('ack')
        if not kinds:
            return False
        self.step_no += 1
        kind = self.rng.choice(kinds)
        if kind == 'call':
            self._issue_call()
        elif kind == 'update':
            self._deliver_update()
        else:
            self._deliver_ack()
        return True

    def _issue_call(self):
        if self._script is not None:
            station, price = self._script.popleft()
        else:
            station = self.rng.choice(list(self.stations))
            price = self.rng.randint(*self.prices)
        self._require_station(station)
        self._remaining_calls -= 1
        self.desired[station] = price
        self.call_log.append(Call(self.step_no, station, price))
        self.app.set_desired_price(station, price)

    def _deliver_update(self):
        i = self.rng.randrange(len(self._in_flight))
        station, price = self._in_flight.pop(i)
        self.stations[station].receive(price)

    def _deliver_ack(self):
        ready = [name for name, s in self.stations.items() if s.acks]
        name = self.rng.choice(ready)
        price = self.stations[name].acks.popleft()
        self.ack_log.append(Ack(self.step_no, name, price))
        self.app.receive_acknowledgement(name, price)

    def run(self, max_steps=None):
        n = 0
        while (max_steps is None or n < max_steps) and self.step():
            n += 1
        return n

    def is_quiet(self):
        return (self._remaining_calls == 0 and not self._in_flight
                and not any(s.acks for s in self.stations.values()))

    def displayed(self, station):
        return self.stations[station].displayed

    def query(self, station):
        return self.app.query_station_state(station)

    def in_flight(self):
        return list(self._in_flight)

    def pending_acks(self, station=None):
        if station is not None:
            return len(self.stations[station].acks)
        return sum(len(s.acks) for s in self.stations.values())

    def last_ack_price(self, station):
        for ack in reversed(self.ack_log):
            if ack.station == station:
                return ack.price
        return None
