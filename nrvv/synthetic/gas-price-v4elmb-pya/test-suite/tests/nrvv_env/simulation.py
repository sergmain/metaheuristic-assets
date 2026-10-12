'''Deterministic simulation of the clients and transport around the server side.

The server side is handed in by the test as a factory that receives the
SendPriceUpdate port, ``send_price_update(station, seq, price)``, and returns
an object exposing ``set_desired_price``, ``ack_received``, ``tick`` and
``query_station_state``.

Per tick, in this order:
  1. the scripted SetDesiredPrice calls for the tick are made;
  2. the service's ``tick`` is called;
  3. updates due at this tick are delivered to their stations;
  4. acknowledgements due at this tick are delivered to the service.
Every transmission has a delay of at least one tick.
'''
import copy
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

MAX_DELAY = 6          # ticks; bound on every channel delay
DROP_RATE = 0.15       # chance one copy of an update is lost on the station channel
DUPLICATE_RATE = 0.10  # chance an update is transmitted twice on the station channel
MAX_OUTAGES = 2        # outage windows per station, at most
MAX_OUTAGE_LENGTH = 15
PRICE_RANGE = 20       # scripted prices are drawn from 0..PRICE_RANGE


@dataclass
class ScriptedChange:
    tick: int
    station: str
    price: int


@dataclass
class ChangeRecord:
    '''A SetDesiredPrice call as made, with the service state just before it.'''
    tick: int
    station: str
    price: int
    state_before: Dict[str, Any]


@dataclass
class SendRecord:
    '''A call of the SendPriceUpdate port, with the service state just before the call that made it.'''
    tick: int
    station: str
    seq: int
    price: int
    state_before: Dict[str, Any]


@dataclass
class Delivery:
    '''An update arriving at a station; ``order`` counts updates that station received so far.'''
    tick: int
    station: str
    seq: int
    price: int
    order: int


@dataclass
class AckRecord:
    '''An acknowledgement produced by a station, with its arrival tick; ``lost`` if it never arrived.'''
    station: str
    seq: int
    produced: int
    arrives: int
    lost: bool


@dataclass
class AckDelivery:
    '''An acknowledgement handed to the service; ``order`` counts acknowledgements from that station.'''
    tick: int
    station: str
    seq: int
    order: int


class Station:
    '''Holds only the price of the last update it received; acknowledges every update.'''

    def __init__(self, station_id: str):
        self.id = station_id
        self.price: Optional[int] = None

    def receive(self, seq: int, price: int) -> int:
        self.price = price
        return seq


class Simulation:
    def __init__(self, seed, service_factory: Any, *, stations: int = 4,
                 active_ticks: int = 120, quiet_ticks: int = 256):
        self.seed = seed
        self.rng = random.Random(seed)
        self.station_ids = [f'station-{i}' for i in range(stations)]
        self.stations = {s: Station(s) for s in self.station_ids}
        self.active_ticks = active_ticks
        self.quiet_ticks = quiet_ticks
        self.end_tick = active_ticks + quiet_ticks

        self.script: List[ScriptedChange] = self._generate_script()
        self.outages: Dict[str, List[Tuple[int, int]]] = self._generate_outages()

        self.tick = 0
        self.sends: List[SendRecord] = []
        self.changes: List[ChangeRecord] = []
        self.deliveries: List[Delivery] = []
        self.acks: List[AckRecord] = []
        self.acknowledged: List[AckDelivery] = []

        self._changes_at = defaultdict(list)
        for change in self.script:
            self._changes_at[change.tick].append(change)
        self._to_station = defaultdict(list)   # due tick -> [(station, seq, price)]
        self._to_server = defaultdict(list)    # due tick -> [AckRecord]
        self._last_ack_arrival = {s: 0 for s in self.station_ids}
        self._received = {s: 0 for s in self.station_ids}
        self._acked = {s: 0 for s in self.station_ids}
        self._before: Optional[Dict[str, Any]] = None

        self.service = None
        self.service = service_factory(self._send_price_update)

    # ----- seeded generation -------------------------------------------------

    def _generate_script(self) -> List[ScriptedChange]:
        rng = self.rng
        script = []
        for station in self.station_ids:
            used = set()
            history: List[int] = []
            current: Optional[int] = None
            for _burst in range(rng.randint(2, 5)):
                tick = rng.randint(1, self.active_ticks)
                for _k in range(rng.randint(1, 4)):
                    if tick > self.active_ticks:
                        break
                    if tick not in used:
                        price = self._next_price(current, history)
                        script.append(ScriptedChange(tick, station, price))
                        used.add(tick)
                        history.append(price)
                        current = price
                    # short gaps keep several changes in flight at once
                    tick += rng.randint(1, 3)
        script.sort(key=lambda c: (c.tick, c.station))
        return script

    def _next_price(self, current: Optional[int], history: List[int]) -> int:
        rng = self.rng
        earlier = [p for p in history if p != current]
        roll = rng.random()
        if earlier and roll < 0.35:
            return rng.choice(earlier)          # back to a previously shown price
        if roll < 0.40 and current is not None:
            return current                      # same price again
        while True:
            price = rng.randint(0, PRICE_RANGE)
            if price != current:
                return price

    def _generate_outages(self) -> Dict[str, List[Tuple[int, int]]]:
        outages = {}
        for station in self.station_ids:
            windows = []
            for _w in range(self.rng.randint(0, MAX_OUTAGES)):
                start = self.rng.randint(1, self.active_ticks)
                length = self.rng.randint(1, MAX_OUTAGE_LENGTH)
                windows.append((start, start + length))
            outages[station] = sorted(windows)
        return outages

    # ----- driving -----------------------------------------------------------

    @property
    def done(self) -> bool:
        return self.tick >= self.end_tick

    def step(self) -> int:
        if self.done:
            raise RuntimeError('simulation already finished')
        self.tick += 1
        now = self.tick
        for change in self._changes_at.get(now, ()):
            before = self._call('set_desired_price', change.station, change.price)
            self.changes.append(ChangeRecord(now, change.station, change.price, before))
        self._call('tick', now)
        for station, seq, price in self._to_station.pop(now, ()):
            self._deliver_update(now, station, seq, price)
        for ack in self._to_server.pop(now, ()):
            self._deliver_ack(now, ack)
        return now

    def run(self) -> 'Simulation':
        while not self.done:
            self.step()
        return self

    def in_transit(self) -> int:
        return (sum(len(v) for v in self._to_station.values())
                + sum(len(v) for v in self._to_server.values()))

    def query(self, station: str) -> Any:
        return self.service.query_station_state(station)

    def reachable(self, station: str, tick: int) -> bool:
        return not any(start <= tick < end for start, end in self.outages[station])

    def reachable_at_end(self, station: str) -> bool:
        return self.reachable(station, self.end_tick)

    def final_desired(self, station: str) -> Optional[int]:
        prices = [c.price for c in self.script if c.station == station]
        return prices[-1] if prices else None

    # ----- service calls and channels ----------------------------------------

    def _snapshot(self) -> Dict[str, Any]:
        if self.service is None:
            return {}
        return {s: copy.deepcopy(self.service.query_station_state(s)) for s in self.station_ids}

    def _call(self, method: str, *args) -> Dict[str, Any]:
        before = self._snapshot()
        self._before = before
        try:
            getattr(self.service, method)(*args)
        finally:
            self._before = None
        return before

    def _send_price_update(self, station: str, seq: int, price: int) -> None:
        if station not in self.stations:
            raise KeyError(station)
        now = self.tick
        before = self._before if self._before is not None else self._snapshot()
        self.sends.append(SendRecord(now, station, seq, price, before))
        if not self.reachable(station, now):
            return
        copies = 2 if self.rng.random() < DUPLICATE_RATE else 1
        for _c in range(copies):
            if self.rng.random() < DROP_RATE:
                continue
            due = now + self.rng.randint(1, MAX_DELAY)
            self._to_station[due].append((station, seq, price))

    def _deliver_update(self, now: int, station: str, seq: int, price: int) -> None:
        if not self.reachable(station, now):
            return
        order = self._received[station]
        self._received[station] += 1
        self.deliveries.append(Delivery(now, station, seq, price, order))
        ack_seq = self.stations[station].receive(seq, price)
        self._produce_ack(now, station, ack_seq)

    def _produce_ack(self, now: int, station: str, seq: int) -> None:
        arrives = max(now + self.rng.randint(1, MAX_DELAY), self._last_ack_arrival[station])
        self._last_ack_arrival[station] = arrives
        ack = AckRecord(station, seq, now, arrives, not self.reachable(station, arrives))
        self.acks.append(ack)
        if not ack.lost:
            self._to_server[arrives].append(ack)

    def _deliver_ack(self, now: int, ack: AckRecord) -> None:
        order = self._acked[ack.station]
        self._acked[ack.station] += 1
        self.acknowledged.append(AckDelivery(now, ack.station, ack.seq, order))
        self._call('ack_received', ack.station, ack.seq)
