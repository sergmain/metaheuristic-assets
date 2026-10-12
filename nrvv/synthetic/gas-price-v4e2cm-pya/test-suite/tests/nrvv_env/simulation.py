'''Simulated Environment of the server side: clients, transport and stations.

Time is a logical tick counter advanced only by Simulation.step(). The single
random.Random(seed) instance is the only source of randomness.
'''

import heapq
import random
from dataclasses import dataclass
from typing import Any, Optional

DMAX = 5

SET_OPERATION = 'set_desired_price'
STATUS_OPERATION = 'get_station_status'
TICK_OPERATION = 'clock_tick'
SEND_PORT_NAMES = ('set_send_port', 'set_price_update_sender', 'set_update_sender', 'set_sender', 'register_send_port')
ACK_RECEIVER_NAMES = ('receive_acknowledgement', 'receive_ack', 'acknowledge', 'on_acknowledgement', 'handle_acknowledgement', 'on_ack')
STATUS_FIELDS = ('desired_price', 'confirmed_price', 'in_flight_price', 'in_flight_sent_at')


class NotQuiescent(RuntimeError):
    '''The system did not reach quiescence within the tick bound.'''


@dataclass
class SetCall:
    station: Any
    price: Any
    time: int
    result: Any


@dataclass
class SentUpdate:
    station: Any
    price: Any
    sent_at: int
    desired_at_send: Any     # latest desired price accepted by the clients at send time
    confirmed_at_send: Any   # service's confirmed price at send time (GetStationStatus)
    in_flight_at_send: Any   # service's in-flight price at send time (GetStationStatus)
    dropped: bool = False    # lost by the transport or during a station outage
    arrival: Optional[int] = None
    delivered_at: Optional[int] = None
    acked_at: Optional[int] = None


@dataclass
class Delivery:
    station: Any
    price: Any
    time: int


@dataclass
class Acknowledgement:
    station: Any
    price: Any
    receipt_time: int  # tick at which the station received the update
    time: int          # tick at which the acknowledgement reached the service


@dataclass
class StatusObservation:
    station: Any
    time: int
    raw: Any


class Station:
    '''Simulated station: displays the price of its last received update and acknowledges every one.'''

    def __init__(self, station_id, outages):
        self.id = station_id
        self.outages = outages  # half-open (start, end) tick intervals
        self.displayed = None
        self.sent_count = 0       # updates the service sent to this station
        self.delivered_count = 0  # updates the station received
        self.ack_count = 0        # acknowledgements the station returned

    def in_outage(self, tick):
        return any(start <= tick < end for start, end in self.outages)


class Simulation:
    '''Connects the server side to the simulated clients, transport and stations.

    One step() is one tick: the transport delivers the updates due at the new tick
    (stations display them and return acknowledgements), then the acknowledgements
    due are handed to the service, then the service's clock_tick runs.
    '''

    def __init__(self, service, seed, stations, *, dmax=DMAX, loss=0.2, horizon=60,
                 max_outage=8, max_outages_per_station=3,
                 send_port_name=None, ack_receiver_name=None):
        if dmax < 1:
            raise ValueError('dmax must be at least 1')
        self.service = service
        self.seed = seed
        self.dmax = dmax
        self.loss = loss
        self.now = 0
        self._rng = random.Random(seed)
        self.stations = {}
        for station_id in stations:
            outages = []
            for _ in range(self._rng.randint(0, max_outages_per_station)):
                start = self._rng.randrange(horizon)
                outages.append((start, start + self._rng.randint(1, max_outage)))
            self.stations[station_id] = Station(station_id, outages)
        self.last_desired = {station_id: None for station_id in self.stations}
        self.sent = []
        self.deliveries = []
        self.acks = []
        self.set_calls = []
        self.status_log = []
        self._updates = []  # heap of (arrival, seq, SentUpdate)
        self._acks = []     # heap of (arrival, seq, SentUpdate, receipt_time)
        self._last_ack_arrival = {station_id: 0 for station_id in self.stations}
        self._seq = 0
        self._attach(send_port_name, ack_receiver_name)

    def _attach(self, send_port_name, ack_receiver_name):
        send_port_name = send_port_name or _first_callable(self.service, SEND_PORT_NAMES)
        ack_receiver_name = ack_receiver_name or _first_callable(self.service, ACK_RECEIVER_NAMES)
        if send_port_name is None or ack_receiver_name is None:
            raise LookupError('cannot find the send port setter or the acknowledgement receiver of the service; pass send_port_name and ack_receiver_name')
        getattr(self.service, send_port_name)(self._send_port)
        self._ack_receiver = getattr(self.service, ack_receiver_name)

    # Clients: the test-facing operations of the central service's clients

    def set_desired_price(self, station_id, price):
        self.last_desired[station_id] = price
        result = getattr(self.service, SET_OPERATION)(station_id, price)
        self.set_calls.append(SetCall(station_id, price, self.now, result))
        return result

    def get_station_status(self, station_id):
        raw = getattr(self.service, STATUS_OPERATION)(station_id)
        self.status_log.append(StatusObservation(station_id, self.now, raw))
        return raw

    def make_schedule(self, length, burst_rate=0.15, set_rate=0.35, max_burst=5, max_price=99):
        ids = list(self.stations)
        events = []
        while len(events) < length:
            roll = self._rng.random()
            if roll < burst_rate:
                for _ in range(self._rng.randint(2, max_burst)):
                    events.append(('set', self._rng.choice(ids), self._rng.randint(1, max_price)))
            elif roll < burst_rate + set_rate:
                events.append(('set', self._rng.choice(ids), self._rng.randint(1, max_price)))
            else:
                events.append(('tick',))
        return events[:length]

    def run(self, events):
        for event in events:
            if event[0] == 'set':
                self.set_desired_price(event[1], event[2])
            elif event[0] == 'tick':
                self.step()
            else:
                raise ValueError('unknown event: %r' % (event,))

    def run_scenario(self, length, max_ticks=500):
        events = self.make_schedule(length)
        self.run(events)
        self.quiesce(max_ticks)
        return events

    # Time and transport

    def step(self):
        self.now += 1
        now = self.now
        while self._updates and self._updates[0][0] <= now:
            _, _, update = heapq.heappop(self._updates)
            station = self.stations[update.station]
            if station.in_outage(now):
                update.dropped = True
                continue
            station.displayed = update.price
            station.delivered_count += 1
            station.ack_count += 1
            update.delivered_at = now
            self.deliveries.append(Delivery(update.station, update.price, now))
            # Per-station FIFO; never later than receipt + dmax, since earlier receipts have earlier arrivals.
            arrival = max(now + self._rng.randint(1, self.dmax), self._last_ack_arrival[update.station])
            self._last_ack_arrival[update.station] = arrival
            heapq.heappush(self._acks, (arrival, self._next_seq(), update, now))
        while self._acks and self._acks[0][0] <= now:
            _, _, update, receipt = heapq.heappop(self._acks)
            update.acked_at = now
            self.acks.append(Acknowledgement(update.station, update.price, receipt, now))
            self._ack_receiver(update.station)
        getattr(self.service, TICK_OPERATION)()

    def quiesce(self, max_ticks=500):
        ticks = 0
        while not self.is_quiescent():
            if ticks >= max_ticks:
                raise NotQuiescent('not quiescent after %d ticks' % max_ticks)
            self.step()
            ticks += 1
        return ticks

    def is_quiescent(self):
        if self._updates or self._acks:
            return False
        for station_id in self.stations:
            desired, confirmed, in_flight, _ = self._query(station_id)
            if in_flight is not None or confirmed != desired:
                return False
        return True

    def in_flight_messages(self):
        return len(self._updates) + len(self._acks)

    # Observation

    def displayed(self, station_id):
        return self.stations[station_id].displayed

    def sent_count(self, station_id):
        return self.stations[station_id].sent_count

    def sent_updates(self, station_id=None):
        return [u for u in self.sent if station_id is None or u.station == station_id]

    def last_delivered(self, station_id):
        for delivery in reversed(self.deliveries):
            if delivery.station == station_id:
                return delivery
        return None

    # Port implementations handed to the service

    def _send_port(self, station_id, price):
        station = self.stations[station_id]
        _, confirmed, in_flight, _ = self._query(station_id)
        station.sent_count += 1
        update = SentUpdate(station_id, price, self.now, self.last_desired[station_id], confirmed, in_flight)
        self.sent.append(update)
        lost = self._rng.random() < self.loss
        delay = self._rng.randint(1, self.dmax)
        if lost:
            update.dropped = True
        else:
            update.arrival = self.now + delay
            heapq.heappush(self._updates, (update.arrival, self._next_seq(), update))

    def _query(self, station_id):
        return _status_fields(getattr(self.service, STATUS_OPERATION)(station_id))

    def _next_seq(self):
        self._seq += 1
        return self._seq


def _first_callable(obj, names):
    for name in names:
        if callable(getattr(obj, name, None)):
            return name
    return None


def _status_fields(raw):
    if isinstance(raw, dict):
        values = [raw.get(name) for name in STATUS_FIELDS]
    elif isinstance(raw, (tuple, list)):
        values = list(raw) + [None] * (len(STATUS_FIELDS) - len(raw))
    else:
        values = [getattr(raw, name, None) for name in STATUS_FIELDS]
    return tuple(values[:len(STATUS_FIELDS)])
