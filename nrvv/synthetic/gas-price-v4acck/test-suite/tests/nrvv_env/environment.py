'''Simulated environment around the server side: upstream price source, transport,
station clients, logical clock and traffic log.

Deterministic: all randomness comes from one random.Random(seed); no threads, real time
or I/O. This module never imports the server side. A test binds it with
Simulation.bind(server), or passes Simulation.send_price_update into the server, then
drives it with step(), run_until(t), run_until_idle() or run_to_end().
'''

import heapq
import random
from dataclasses import dataclass
from typing import Any, Dict, Hashable, List, Optional, Tuple

MAX_DELAY = 60  # logical seconds, for transport delay and station acknowledgement delay


@dataclass(frozen=True)
class PriceChange:
    '''One SetLatestPrice call made by the upstream price source.'''
    time: int
    station: Hashable
    price: Any


@dataclass
class SendRecord:
    '''One SendPriceUpdate seen on the outbound port, with its delivery and acknowledgement times.'''
    sent_at: int
    station: Hashable
    price: Any
    delivered_at: Optional[int] = None
    acknowledged_at: Optional[int] = None


class StationClient:
    '''Dumb station: applies each delivered price, acknowledges in delivery order.'''

    def __init__(self, station):
        self.station = station
        self.held_price = None
        self.deliveries: List[Tuple[int, Any]] = []  # (time, price) in delivery order
        self.acknowledgements: List[int] = []  # times the acknowledgements were returned
        self._ack_due = 0  # latest scheduled ack time, keeps acks in delivery order

    def apply(self, time, price):
        self.held_price = price
        self.deliveries.append((time, price))

    def ack_time(self, delivered_at, delay):
        self._ack_due = max(self._ack_due, delivered_at + delay)
        return self._ack_due


_CHANGE = 'change'
_DELIVER = 'deliver'
_ACK = 'ack'


class Simulation:
    '''The environment: seeded change sequence, seeded transport, station clients, logical clock.

    Logical time starts at 0 and advances one second per step(). Each step calls
    server.tick(now) first, then processes every event due at now in scheduling order:
    SetLatestPrice calls, deliveries to stations, and acknowledgements to the server.
    '''

    def __init__(self, seed, stations, *, window=600, quiet=900, changes_per_station=(1, 4),
                 price_range=(1, 20), max_steps=100000):
        if changes_per_station[0] < 1:
            raise ValueError('each station needs at least one change')
        self.seed = seed
        self.window = window
        self.end_time = window + quiet
        self.max_steps = max_steps
        self.now = 0
        self.stations: Dict[Hashable, StationClient] = {s: StationClient(s) for s in stations}
        self.changes: List[PriceChange] = []
        self.sends: List[SendRecord] = []
        self.deliveries: List[Tuple[int, Hashable, Any]] = []  # (time, station, price)
        self.acknowledgements: List[Tuple[int, Hashable]] = []  # (time, station)
        self.reference_final_prices: Dict[Hashable, Any] = {}
        self._rng = random.Random(seed)
        self._heap: List[Tuple[int, int, str, Any]] = []
        self._seq = 0
        self._server = None
        self._generate_changes(changes_per_station, price_range)

    def _push(self, time, kind, payload):
        seq = self._seq
        self._seq += 1
        heapq.heappush(self._heap, (time, seq, kind, payload))
        return seq

    def _generate_changes(self, counts, prices):
        scheduled = []
        for station in self.stations:
            for _ in range(self._rng.randint(*counts)):
                time = self._rng.randint(0, self.window)
                price = self._rng.randint(*prices)
                seq = self._push(time, _CHANGE, (station, price))
                scheduled.append((time, seq, station, price))
        # The last change in (time, seq) order is the station's final desired price.
        for time, seq, station, price in sorted(scheduled, key=lambda c: (c[0], c[1])):
            self.reference_final_prices[station] = price

    def bind(self, server):
        '''Connect the server side: its outbound port becomes send_price_update.'''
        self._server = server
        server.send_price_update = self.send_price_update
        return server

    def send_price_update(self, station, price):
        '''Outbound port: record the send and schedule its delivery after a seeded delay.'''
        if station not in self.stations:
            raise KeyError(station)
        record = SendRecord(sent_at=self.now, station=station, price=price)
        self.sends.append(record)
        self._push(self.now + self._rng.randint(0, MAX_DELAY), _DELIVER, record)

    def step(self):
        '''Advance one logical second, processing everything due at the current time.'''
        if self._server is None:
            raise RuntimeError('bind a server side before stepping')
        t = self.now
        self._server.tick(t)
        while self._heap and self._heap[0][0] <= t:
            _, _, kind, payload = heapq.heappop(self._heap)
            if kind == _CHANGE:
                station, price = payload
                self.changes.append(PriceChange(t, station, price))
                self._server.set_latest_price(station, price)
            elif kind == _DELIVER:
                record = payload
                client = self.stations[record.station]
                client.apply(t, record.price)
                record.delivered_at = t
                self.deliveries.append((t, record.station, record.price))
                ack_at = client.ack_time(t, self._rng.randint(0, MAX_DELAY))
                self._push(ack_at, _ACK, record)
            else:
                record = payload
                self.stations[record.station].acknowledgements.append(t)
                record.acknowledged_at = t
                self.acknowledgements.append((t, record.station))
                self._server.acknowledgement_received(record.station)
        self.now += 1
        return t

    @property
    def in_flight(self):
        '''Number of events not yet processed: pending changes, deliveries and acknowledgements.'''
        return len(self._heap)

    def _advance(self, keep_going):
        steps = 0
        while keep_going():
            if steps >= self.max_steps:
                raise RuntimeError('simulation exceeded max_steps')
            self.step()
            steps += 1

    def run_until(self, time):
        '''Step until logical time time has been processed.'''
        self._advance(lambda: self.now <= time)

    def run_until_idle(self):
        '''Step until nothing is in flight.'''
        self._advance(lambda: bool(self._heap))

    def run_to_end(self):
        '''Step through the change window and quiet period, then until nothing is in flight.'''
        self.run_until(self.end_time)
        self.run_until_idle()

    def send_counts(self):
        '''Total SendPriceUpdate calls per station.'''
        counts = {s: 0 for s in self.stations}
        for record in self.sends:
            counts[record.station] += 1
        return counts

    def held_prices(self):
        '''Held price of every station, for the R1/R2 check.'''
        return {s: c.held_price for s, c in self.stations.items()}

    def unacknowledged_sends(self):
        return [r for r in self.sends if r.acknowledged_at is None]
