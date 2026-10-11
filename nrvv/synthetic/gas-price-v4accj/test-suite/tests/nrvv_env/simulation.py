"""Simulated clients and transport for the server side app.

Deterministic: the only randomness is one random.Random(seed) instance, drawn
in a fixed order, and the only clock is the simulated now. The server is called
only from step; its port calls (send, wake-up request) only record and schedule,
so no call into app is ever nested inside another.
"""

import heapq
import random
from dataclasses import dataclass

PRICE_LOW = 100
PRICE_HIGH = 199
MAX_DELIVERY_DELAY = 20.0
MAX_ACK_LATENCY = 10.0

# Operations the server side must provide, named after the Interface.
APP_OPERATIONS = (
    "set_desired_price",
    "acknowledgement_received",
    "simulated_time_wake_up",
    "query_station_status",
)


@dataclass
class ChangeRecord:
    time: float
    station: object
    price: int
    result: object


@dataclass
class SendRecord:
    index: int
    station: object
    send_id: object
    price: int
    sent_at: float
    state: str = "in_transit"  # in_transit | dropped | delivered | acked
    reason: str = None  # for dropped: "unreachable" | "lost"
    delivered_at: float = None  # also the time the acknowledgement was emitted
    delivery_order: int = None  # position among all deliveries, global
    ack_arrived_at: float = None


@dataclass
class Convergence:
    station: object
    price: int
    changed_at: float
    converged_at: float = None  # None: not applied while this change was the latest


class Simulation:
    """One seeded run: the pricing source, the stations and the transport."""

    def __init__(self, seed, stations=("S1", "S2", "S3"), horizon=1800.0,
                 changes=40, drop_probability=0.15):
        if not isinstance(seed, int):
            raise TypeError("seed must be an int")
        self._stations = tuple(stations)
        if not self._stations:
            raise ValueError("at least one station is required")
        self._rng = random.Random(seed)
        self._horizon = float(horizon)
        self._drop_probability = drop_probability
        self._now = 0.0
        self._seq = 0
        self._queue = []
        self._app = None
        self._pending_changes = 0
        self._schedule = self._make_schedule(changes)
        self._unreachable = {s: self._make_unreachable() for s in self._stations}
        self._desired = {}
        self._applied = {s: None for s in self._stations}
        self._applied_history = {s: [] for s in self._stations}
        self._last_ack_arrival = {s: 0.0 for s in self._stations}
        self._changes = []
        self._sends = []
        self._deliveries = []
        self._acks = []
        for when, station, price in self._schedule:
            self._push(when, "change", (station, price))
            self._pending_changes += 1

    # ----- wiring -------------------------------------------------------

    def connect(self, app):
        """Attach the simulated clients to app through the ports it names.

        The environment's ports are set on app as send_price_update (used by the
        server to send to a station) and request_wake_up (used by the server to
        ask for a simulated-time wake-up).
        """
        for name in APP_OPERATIONS:
            if not callable(getattr(app, name, None)):
                raise TypeError(f"app does not provide {name}")
        self._app = app
        app.send_price_update = self.send_price_update
        app.request_wake_up = self.request_wake_up

    # ----- ports the server calls ---------------------------------------

    def send_price_update(self, station, price, send_id):
        """Port: the server sends a price update to a station. Fire-and-forget."""
        if station not in self._applied:
            raise KeyError(f"unknown station {station!r}")
        record = SendRecord(len(self._sends), station, send_id, price, self._now)
        self._sends.append(record)
        if not self.reachable(station, self._now):
            record.state, record.reason = "dropped", "unreachable"
            return
        if self._rng.random() < self._drop_probability:
            record.state, record.reason = "dropped", "lost"
            return
        delivered_at = self._now + self._rng.uniform(0.0, MAX_DELIVERY_DELAY)
        latency = self._rng.uniform(0.0, MAX_ACK_LATENCY)
        # Acknowledgements return in send order, so never earlier than the previous one
        # for this station. This keeps every arrival within 30 s of its send.
        arrival = max(delivered_at + latency, self._last_ack_arrival[station])
        self._last_ack_arrival[station] = arrival
        self._push(delivered_at, "deliver", record)
        self._push(arrival, "ack", record)

    def request_wake_up(self, at_time):
        """Port: the server asks for simulated_time_wake_up at at_time."""
        self._push(max(float(at_time), self._now), "wake", None)

    # ----- driving ------------------------------------------------------

    def step(self):
        """Process the next scheduled event. Returns False when none is scheduled."""
        if not self._queue:
            return False
        if self._app is None:
            raise RuntimeError("connect an app before running the simulation")
        self._now, _, kind, payload = heapq.heappop(self._queue)
        if kind == "change":
            self._do_change(*payload)
        elif kind == "deliver":
            self._do_deliver(payload)
        elif kind == "ack":
            self._do_ack(payload)
        else:
            self._app.simulated_time_wake_up(self._now)
        return True

    def run_until(self, time):
        """Process every event scheduled up to and including time; then the clock is time."""
        while self._queue and self._queue[0][0] <= time:
            self.step()
        self._now = max(self._now, float(time))

    def run_until_quiet(self, max_events=100000):
        """Process events until nothing is in flight and no price change is pending.

        Wake-ups the server requested beyond the last transport event stay scheduled.
        """
        events = 0
        while self.in_flight() or self._pending_changes:
            if events >= max_events:
                raise RuntimeError(f"not quiet after {max_events} events")
            if not self.step():
                break
            events += 1
        return self._now

    # ----- observation --------------------------------------------------

    @property
    def now(self):
        return self._now

    @property
    def stations(self):
        return self._stations

    def schedule(self):
        """The planned price changes as (time, station, price), fixed by the seed."""
        return list(self._schedule)

    def unreachable_intervals(self, station):
        """Half-open (start, end) intervals during which the station is unreachable."""
        return list(self._unreachable[station])

    def reachable(self, station, time=None):
        when = self._now if time is None else time
        return not any(start <= when < end for start, end in self._unreachable[station])

    def changes(self):
        """Price changes as they were set, with the server's result."""
        return list(self._changes)

    def sends(self):
        """Every send the server made, in send order, with its fate."""
        return list(self._sends)

    def deliveries(self):
        """Delivered sends in delivery order."""
        return list(self._deliveries)

    def acks(self):
        """Acknowledgements in arrival order to the server."""
        return list(self._acks)

    def in_flight(self):
        """Sends whose delivery or acknowledgement is still pending."""
        return sum(1 for r in self._sends if r.state in ("in_transit", "delivered"))

    def desired_price(self, station):
        return self._desired.get(station)

    def applied_price(self, station, at=None):
        """Ground-truth price the station holds now, or at time at."""
        if at is None:
            return self._applied[station]
        value = None
        for when, price in self._applied_history[station]:
            if when > at:
                break
            value = price
        return value

    def applied_history(self, station):
        """Every (time, price) the station applied, in order."""
        return list(self._applied_history[station])

    def convergence(self):
        """For each change: the time the applied price first equals its price.

        The window is the change's own time until the next change to the same station.
        """
        result = []
        for i, change in enumerate(self._changes):
            next_change = next(
                (c.time for c in self._changes[i + 1:] if c.station == change.station),
                float("inf"))
            converged = None
            if self.applied_price(change.station, at=change.time) == change.price:
                converged = change.time
            else:
                for when, price in self._applied_history[change.station]:
                    if change.time <= when < next_change and price == change.price:
                        converged = when
                        break
            result.append(Convergence(change.station, change.price, change.time, converged))
        return result

    def status(self, station):
        """Query the server's station status (read-only)."""
        if self._app is None:
            raise RuntimeError("connect an app before querying it")
        return self._app.query_station_status(station)

    # ----- internals ----------------------------------------------------

    def _push(self, when, kind, payload):
        self._seq += 1
        heapq.heappush(self._queue, (when, self._seq, kind, payload))

    def _do_change(self, station, price):
        self._pending_changes -= 1
        self._desired[station] = price
        result = self._app.set_desired_price(station, price)
        self._changes.append(ChangeRecord(self._now, station, price, result))

    def _do_deliver(self, record):
        record.state = "delivered"
        record.delivered_at = self._now
        record.delivery_order = len(self._deliveries)
        self._deliveries.append(record)
        self._applied[record.station] = record.price
        self._applied_history[record.station].append((self._now, record.price))

    def _do_ack(self, record):
        record.state = "acked"
        record.ack_arrived_at = self._now
        self._acks.append(record)
        self._app.acknowledgement_received(record.station, record.send_id)

    def _make_schedule(self, changes):
        rng = self._rng
        raw = []
        for _ in range(changes):
            when = rng.uniform(0.0, self._horizon)
            station = rng.choice(self._stations)
            raw.append((when, station))
            if rng.random() < 0.3:  # burst: several changes to one station within 60 s
                for _ in range(rng.randint(2, 4)):
                    raw.append((when + rng.uniform(0.0, 60.0), station))
        raw.sort(key=lambda item: item[0])
        desired = {}
        past = {s: [] for s in self._stations}
        schedule = []
        for when, station in raw:
            current = desired.get(station)
            earlier = [p for p in past[station] if p != current]
            if earlier and rng.random() < 0.3:  # back to a previously held price
                price = rng.choice(earlier)
            else:
                price = rng.randint(PRICE_LOW, PRICE_HIGH)
                while price == current:
                    price = rng.randint(PRICE_LOW, PRICE_HIGH)
            desired[station] = price
            past[station].append(price)
            schedule.append((when, station, price))
        return schedule

    def _make_unreachable(self):
        # Reachable gaps are at least 60 s and outages at most 120 s, so every
        # 600 s window holds reachable time. After the horizon all stations are reachable.
        rng = self._rng
        intervals = []
        t = 0.0
        while True:
            t += rng.uniform(60.0, 400.0)
            if t >= self._horizon:
                break
            if rng.random() < 0.5:
                length = rng.uniform(10.0, 120.0)
                intervals.append((t, t + length))
                t += length
        return intervals
