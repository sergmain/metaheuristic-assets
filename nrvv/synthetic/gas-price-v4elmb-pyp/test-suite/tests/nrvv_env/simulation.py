"""Deterministic simulation of the environment of the nrvv price-update service.

The server side (module app) is handed in, never imported. Simulation installs the
outbound port on it and drives its inbound ports, one tick per step:

- the central pricing client calls app.set_desired_price at its scripted ticks;
- each update the server sends through send_price_update (installed as the attribute
  send_price_update of app) reaches its station after a seeded delay, or is dropped,
  or is duplicated, and never altered;
- each acknowledgement a station produces reaches app.ack_received in production order;
- every step ends with app.tick(tick).

Tests read the server through app.query_station_state, via Simulation.server_state.
All randomness comes from random.Random(seed). There is no clock, thread or I/O.
"""
import heapq
import random
from dataclasses import dataclass

OPEN_END = float('inf')
VIEW_FIELDS = ('desired_price', 'shown_price', 'in_flight_seq', 'in_flight_price', 'pending', 'timeout')
MAX_CHANNEL_DELAY = 4
MAX_ACK_DELAY = 3
P_DROP = 0.15
P_DUPLICATE = 0.1
P_REVERT = 0.35
MAX_OUTAGE_LEN = 10
MAX_OUTAGE_WINDOWS = 2
P_OPEN_OUTAGE = 0.1
MAX_PRICE = 20


def normalize_view(result):
    """Return the query result as a dict keyed by VIEW_FIELDS.

    Accepts a dict, a tuple or list in VIEW_FIELDS order, or an object with those attributes.
    """
    if isinstance(result, dict):
        return {f: result.get(f) for f in VIEW_FIELDS}
    if isinstance(result, (tuple, list)):
        values = list(result) + [None] * len(VIEW_FIELDS)
        return dict(zip(VIEW_FIELDS, values))
    return {f: getattr(result, f, None) for f in VIEW_FIELDS}


@dataclass
class Change:
    tick: int
    station: str
    price: object
    view_before: dict
    view_after: dict


@dataclass
class Send:
    tick: int
    station: str
    seq: int
    price: object
    retransmission: bool
    view: dict
    desired: object
    deliveries: list
    dropped: bool


@dataclass
class Delivery:
    tick: int
    station: str
    seq: int
    price: object
    order: int


@dataclass
class Ack:
    station: str
    seq: int
    produced: int
    arrived: object
    dropped: bool


@dataclass
class Station:
    name: str
    price: object = None


class Simulation:
    """One seeded run of the environment around app.

    Attributes for tests: script (tick, station, price), last_change_tick, outages,
    changes, sends, deliveries (per station), acks, stations, desired (per station history).
    """

    def __init__(self, app, seed, stations=4, active_ticks=60, max_timeout=64):
        self.app = app
        self.seed = seed
        self.max_timeout = max_timeout
        if isinstance(stations, int):
            self.station_ids = ['S%d' % i for i in range(stations)]
        else:
            self.station_ids = list(stations)
        self.stations = {s: Station(s) for s in self.station_ids}
        self.tick = 0
        self._rng = random.Random(seed)
        self.script = self._generate_script(active_ticks)
        self.last_change_tick = max(t for t, _, _ in self.script)
        self.outages = self._generate_outages()
        self._script_by_tick = {}
        for t, s, p in self.script:
            self._script_by_tick.setdefault(t, []).append((s, p))
        self.changes = []
        self.sends = []
        self.acks = []
        self.deliveries = {s: [] for s in self.station_ids}
        self.desired = {s: [] for s in self.station_ids}
        self._updates = []
        self._acks = []
        self._ack_clock = {s: 0 for s in self.station_ids}
        self._counter = 0
        self._sent = set()
        app.send_price_update = self.send_price_update

    # ----- seeded generation -----

    def _generate_script(self, active_ticks):
        rng = self._rng
        events = []
        for _ in range(rng.randint(2, 4)):
            index = rng.randrange(len(self.station_ids))
            tick = rng.randint(1, active_ticks)
            for _ in range(rng.randint(1, 4)):
                events.append((tick, index))
                tick += rng.randint(0, 2)
        events.sort()
        current = {}
        history = {s: [] for s in self.station_ids}
        script = []
        for tick, index in events:
            s = self.station_ids[index]
            prior = [p for p in history[s] if p != current.get(s)]
            if prior and rng.random() < P_REVERT:
                price = rng.choice(prior)
            else:
                price = rng.randint(0, MAX_PRICE)
            history[s].append(price)
            current[s] = price
            script.append((tick, s, price))
        return script

    def _generate_outages(self):
        rng = self._rng
        outages = {}
        for s in self.station_ids:
            windows = []
            for _ in range(rng.randint(0, MAX_OUTAGE_WINDOWS)):
                start = rng.randint(1, self.last_change_tick)
                windows.append((start, start + rng.randint(1, MAX_OUTAGE_LEN) - 1))
            if rng.random() < P_OPEN_OUTAGE:
                windows.append((rng.randint(1, self.last_change_tick), OPEN_END))
            outages[s] = windows
        return outages

    # ----- driving -----

    def step(self):
        """Advance one tick: central changes, update deliveries, ack deliveries, then app.tick."""
        self.tick += 1
        tick = self.tick
        for s, p in self._script_by_tick.get(tick, []):
            self._central_change(tick, s, p)
        self._deliver_updates(tick)
        self._deliver_acks(tick)
        self.app.tick(tick)
        return tick

    def run(self, max_ticks=100000):
        """Step until the quiet period has lasted longer than max_timeout and nothing is in flight.

        Stations unreachable at the current tick are excluded from the in-flight check.
        """
        while not self.settled():
            if self.tick >= max_ticks:
                raise RuntimeError('not settled after %d ticks (seed %r)' % (max_ticks, self.seed))
            self.step()
        return self.tick

    def settled(self):
        if self.tick - self.last_change_tick <= self.max_timeout:
            return False
        if self.in_flight():
            return False
        for s in self.station_ids:
            if self.reachable(s) and self.server_state(s)['in_flight_seq'] is not None:
                return False
        return True

    def in_flight(self):
        return bool(self._updates or self._acks)

    # ----- ports and clients -----

    def send_price_update(self, station, seq, price):
        """Outbound port: the transport decides the fate of one sent update."""
        if station not in self.stations:
            raise KeyError(station)
        tick = self.tick
        retransmission = (station, seq) in self._sent
        self._sent.add((station, seq))
        view = self.server_state(station)
        desired = self.desired_at(station, tick)
        copies = []
        if self._rng.random() >= P_DROP:
            for _ in range(2 if self._rng.random() < P_DUPLICATE else 1):
                deliver = tick + self._rng.randint(1, MAX_CHANNEL_DELAY)
                if not self._outage_between(station, tick, deliver):
                    copies.append(deliver)
        self.sends.append(Send(tick, station, seq, price, retransmission, view, desired, copies, not copies))
        for deliver in copies:
            self._counter += 1
            heapq.heappush(self._updates, (deliver, self._counter, station, seq, price))

    def _central_change(self, tick, station, price):
        before = self.server_state(station)
        self.desired[station].append((tick, price))
        self.app.set_desired_price(station, price)
        self.changes.append(Change(tick, station, price, before, self.server_state(station)))

    def _deliver_updates(self, tick):
        while self._updates and self._updates[0][0] <= tick:
            _, _, station, seq, price = heapq.heappop(self._updates)
            self.stations[station].price = price
            self.deliveries[station].append(Delivery(tick, station, seq, price, len(self.deliveries[station])))
            arrival = max(tick + self._rng.randint(1, MAX_ACK_DELAY), self._ack_clock[station])
            self._ack_clock[station] = arrival
            dropped = self._outage_between(station, tick, arrival)
            ack = Ack(station, seq, tick, None if dropped else arrival, dropped)
            self.acks.append(ack)
            if not dropped:
                self._counter += 1
                heapq.heappush(self._acks, (arrival, self._counter, ack))

    def _deliver_acks(self, tick):
        while self._acks and self._acks[0][0] <= tick:
            _, _, ack = heapq.heappop(self._acks)
            self.app.ack_received(ack.station, ack.seq)

    # ----- observation -----

    def server_state(self, station):
        return normalize_view(self.app.query_station_state(station))

    def desired_at(self, station, tick=None):
        if tick is None:
            tick = self.tick
        price = None
        for t, p in self.desired[station]:
            if t <= tick:
                price = p
        return price

    def final_desired(self, station):
        return self.desired_at(station)

    def reachable(self, station, tick=None):
        if tick is None:
            tick = self.tick
        return not any(a <= tick <= b for a, b in self.outages[station])

    def reachable_at_end(self):
        return [s for s in self.station_ids if self.reachable(s)]

    def final_display_mismatches(self):
        """(station, shown, desired) for each station reachable at the end whose shown price differs."""
        result = []
        for s in self.reachable_at_end():
            shown = self.stations[s].price
            want = self.final_desired(s)
            if shown != want:
                result.append((s, shown, want))
        return result

    def _outage_between(self, station, start, end):
        return any(a <= end and b >= start for a, b in self.outages[station])
