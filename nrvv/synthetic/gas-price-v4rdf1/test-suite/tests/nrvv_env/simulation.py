'''Deterministic simulated environment for the NRVV server side.

Logical time is a step counter. Each step issues one client call, delivers one
in-flight update, or delivers one acknowledgement, chosen by a seeded scheduler.
A run is quiet when no client calls remain and no message is pending.
'''

import collections
import random


SentUpdate = collections.namedtuple('SentUpdate', 'update_id step station price')
DeliveredUpdate = collections.namedtuple('DeliveredUpdate', 'update_id step station price')
DeliveredAck = collections.namedtuple('DeliveredAck', 'update_id step station price')
ClientCall = collections.namedtuple('ClientCall', 'step client station price')
Notice = collections.namedtuple('Notice', 'step station price')

_InFlight = collections.namedtuple('_InFlight', 'update_id station price')
_PendingAck = collections.namedtuple('_PendingAck', 'update_id price')


class Clock:
    '''Logical time: a step counter advanced once per simulation step.'''

    def __init__(self):
        self.now = 0


class Station:
    '''Keeps one displayed price and a FIFO queue of acknowledgements.'''

    def __init__(self, name):
        self.name = name
        self.displayed = None
        self.acks = collections.deque()

    def receive(self, update_id, price):
        self.displayed = price
        self.acks.append(_PendingAck(update_id, price))


class CentralClient:
    '''A central client that issues its planned SetDesiredPrice calls in order.'''

    def __init__(self, name, plan):
        self.name = name
        self.plan = collections.deque(plan)


class PricingTeam:
    '''Recipient of pricing notices; records each with its logical arrival time.'''

    def __init__(self, clock):
        self._clock = clock
        self.notices = []

    def receive(self, station, price):
        self.notices.append(Notice(self._clock.now, station, price))


class Simulation:
    '''One seeded run of the simulated environment around a server.

    make_server(send_update, send_pricing_notice) must return an object with
    set_desired_price(station, price), receive_acknowledgement(station, price)
    and query_station_state(station). If make_server is not callable it is used
    as the server object as it is.

    script, if given, is a list with one plan per client; each plan is a list of
    (station, price) pairs. Otherwise each client gets 'calls' random
    (station, price) pairs drawn from the seed.
    '''

    def __init__(self, seed, make_server, stations, script=None, clients=3, calls=10,
                 prices=tuple(range(1, 101))):
        self.seed = seed
        self._rng = random.Random(seed)
        self.clock = Clock()
        self.station_names = list(stations)
        if not self.station_names:
            raise ValueError('at least one station is needed')
        self.stations = {name: Station(name) for name in self.station_names}
        self.pricing = PricingTeam(self.clock)
        self.sent = []
        self.delivered_updates = []
        self.delivered_acks = []
        self.client_calls = []
        self._in_flight = []
        self._last_update_id = 0

        if script is None:
            plans = []
            for _ in range(clients):
                plans.append([(self._rng.choice(self.station_names), self._rng.choice(prices))
                              for _ in range(calls)])
        else:
            plans = [list(plan) for plan in script]
        for plan in plans:
            for station, _ in plan:
                self._require_station(station)
        self._clients = [CentralClient(i, plan) for i, plan in enumerate(plans)]

        if callable(make_server):
            self.server = make_server(self.send_update, self.send_pricing_notice)
        else:
            self.server = make_server

    # Outbound ports, called by the server.

    def send_update(self, station, price):
        self._require_station(station)
        self._last_update_id += 1
        self.sent.append(SentUpdate(self._last_update_id, self.clock.now, station, price))
        self._in_flight.append(_InFlight(self._last_update_id, station, price))

    def send_pricing_notice(self, station, price):
        self.pricing.receive(station, price)

    # Logical time and scheduling.

    @property
    def quiet(self):
        return not (self._in_flight
                    or any(client.plan for client in self._clients)
                    or any(station.acks for station in self.stations.values()))

    def step(self):
        '''Runs one step; returns False (and does not advance time) if the run is quiet.'''
        kinds = []
        if any(client.plan for client in self._clients):
            kinds.append('call')
        if self._in_flight:
            kinds.append('update')
        if any(station.acks for station in self.stations.values()):
            kinds.append('ack')
        if not kinds:
            return False
        self.clock.now += 1
        kind = self._rng.choice(kinds)
        if kind == 'call':
            self._issue_call()
        elif kind == 'update':
            self._deliver_update()
        else:
            self._deliver_ack()
        return True

    def run(self, max_steps=None):
        '''Steps until quiet; returns the number of steps taken.'''
        steps = 0
        while not self.quiet:
            if max_steps is not None and steps >= max_steps:
                raise RuntimeError(f'not quiet after {max_steps} steps')
            self.step()
            steps += 1
        return steps

    def _issue_call(self):
        client = self._rng.choice([c for c in self._clients if c.plan])
        station, price = client.plan.popleft()
        self.client_calls.append(ClientCall(self.clock.now, client.name, station, price))
        self.server.set_desired_price(station, price)

    def _deliver_update(self):
        message = self._in_flight.pop(self._rng.randrange(len(self._in_flight)))
        self.stations[message.station].receive(message.update_id, message.price)
        self.delivered_updates.append(
            DeliveredUpdate(message.update_id, self.clock.now, message.station, message.price))

    def _deliver_ack(self):
        station = self._rng.choice([s for s in self.stations.values() if s.acks])
        ack = station.acks.popleft()
        self.delivered_acks.append(DeliveredAck(ack.update_id, self.clock.now, station.name, ack.price))
        self.server.receive_acknowledgement(station.name, ack.price)

    # Observation. None of these changes simulated state.

    def displayed(self, station):
        return self.stations[station].displayed

    def query(self, station):
        return self.server.query_station_state(station)

    def desired_at(self, station, step):
        '''The desired price clients had set for the station by the given step, or None.'''
        price = None
        for call in self.client_calls:
            if call.step > step:
                break
            if call.station == station:
                price = call.price
        return price

    def latest_desired(self, station):
        return self.desired_at(station, self.clock.now)

    def last_ack(self, station):
        '''The last acknowledgement delivered for the station, or None.'''
        for ack in reversed(self.delivered_acks):
            if ack.station == station:
                return ack
        return None

    def _require_station(self, station):
        if station not in self.stations:
            raise KeyError(f'unknown station {station!r}')
