"""Simulated environment for the server side ``app`` (GASV4PRDA-26..30).

Only the clients and the transport are simulated here: the central service,
the stations and the messages between them. Nothing implements the server.
Everything is deterministic: randomness comes only from random.Random
instances built from the seed, and logical time moves only through
``Simulation.step()``.

Typical use from a test::

    import app
    from nrvv_env import Simulation

    sim = Simulation(seed=7, server=app)   # module, instance, or factory
    sim.run_until_idle()                   # drive until nothing is in flight
    sim.stations["S1"].display             # what station S1 shows now
    sim.send_calls                         # every call of the send port, with time
"""

import bisect
import heapq
import itertools
import random
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

__all__ = [
    "AckCall",
    "CentralService",
    "DesiredChange",
    "Message",
    "SendCall",
    "Simulation",
    "Station",
]

# One-way transport bound in logical seconds, the same in both directions (GASV4PRDA-28).
MAX_DELAY = 5

# Operations the server side must provide (GASV4PRDA-22, -23, -24).
SERVER_OPERATIONS = ("desired_price_change", "acknowledgement_received", "advance_time")


class SendCall(NamedTuple):
    """One call of the send port by the server (GASV4PRDA-25)."""

    time: int
    station_id: str
    sequence_number: int
    price: Any


class AckCall(NamedTuple):
    """One acknowledgement delivered to the server (GASV4PRDA-23)."""

    time: int
    station_id: str
    sequence_number: int


class DesiredChange(NamedTuple):
    """One desired-price change issued by the central service (GASV4PRDA-22)."""

    time: int
    station_id: str
    price: Any


class Message:
    """One copy of an update or an acknowledgement, from send to outcome."""

    def __init__(self, kind, station_id, sequence_number, price, sent_at, duplicate=False):
        self.kind = kind  # "update" or "ack"
        self.station_id = station_id
        self.sequence_number = sequence_number
        self.price = price  # None for acknowledgements
        self.sent_at = sent_at
        self.duplicate = duplicate  # True for the extra copy of a duplicated update
        self.due_at: Optional[int] = None  # delivery time, once scheduled
        self.delivered_at: Optional[int] = None
        # "in_flight", "delivered", "lost" or "dropped" (station unreachable)
        self.status = "in_flight"


class _Reachability:
    """Seeded alternating up/down intervals of one station, generated on demand.

    The intervals depend only on the seed of the station, not on the order
    in which they are queried.
    """

    def __init__(self, rng, enabled, up_range, down_range):
        self._rng = rng
        self._enabled = enabled
        self._up_range = up_range
        self._down_range = down_range
        self._starts: List[float] = []
        self._ends: List[float] = []
        self._is_up: List[bool] = []
        self._next_start = 0
        self._next_is_up = True

    def _extend(self, t):
        while not self._ends or self._ends[-1] <= t:
            if not self._enabled:
                length = float("inf")
            elif self._next_is_up:
                length = self._rng.randint(*self._up_range)
            else:
                length = self._rng.randint(*self._down_range)
            self._starts.append(self._next_start)
            self._ends.append(self._next_start + length)
            self._is_up.append(self._next_is_up)
            self._next_start += length
            self._next_is_up = not self._next_is_up

    def _interval(self, t):
        if t < 0:
            raise ValueError("logical time starts at 0")
        self._extend(t)
        return bisect.bisect_right(self._starts, t) - 1

    def reachable_at(self, t):
        return self._is_up[self._interval(t)]

    def reachable_throughout(self, start, end):
        """True if the station is reachable at every whole second in [start, end]."""
        self._extend(end)
        i = self._interval(start)
        while i < len(self._starts) and self._starts[i] <= end:
            if not self._is_up[i]:
                return False
            i += 1
        return True


class Station:
    """A simulated station: shows the last update copy it received, acknowledges every copy."""

    def __init__(self, station_id, reachability):
        self.station_id = station_id
        self.display_history: List[Tuple[int, Any]] = []  # (time, price) at each display change
        self.received: List[Tuple[int, int, Any]] = []  # (time, sequence_number, price) per copy
        self._reachability = reachability

    @property
    def display(self):
        return self.display_history[-1][1] if self.display_history else None

    def display_at(self, t):
        price = None
        for when, value in self.display_history:
            if when > t:
                break
            price = value
        return price

    def reachable_at(self, t):
        return self._reachability.reachable_at(t)

    def reachable_throughout(self, start, end):
        return self._reachability.reachable_throughout(start, end)


class CentralService:
    """Scripted central service: at each logical second a station may get a new desired price.

    A new price is always different from the station's current desired price,
    but may be an earlier price (a reversion). The client never sends sequence
    numbers or acknowledgements.
    """

    def __init__(self, rng, station_ids, prices, change_rate, horizon):
        self._rng = rng
        self._station_ids = list(station_ids)
        self._prices = tuple(dict.fromkeys(prices))
        if len(self._prices) < 2:
            raise ValueError("at least two distinct prices are needed")
        self._change_rate = change_rate
        self._horizon = horizon
        self.desired: Dict[str, Any] = {sid: None for sid in self._station_ids}
        self.changes: List[DesiredChange] = []

    def issue(self, t):
        """Pick this second's changes; return them as (station_id, price) pairs."""
        if t > self._horizon:
            return []
        issued = []
        for sid in self._station_ids:
            if self._rng.random() >= self._change_rate:
                continue
            current = self.desired[sid]
            choices = [p for p in self._prices if p != current]
            price = self._rng.choice(choices)
            self.desired[sid] = price
            self.changes.append(DesiredChange(t, sid, price))
            issued.append((sid, price))
        return issued

    def desired_at(self, station_id, t):
        price = None
        for change in self.changes:
            if change.time > t:
                break
            if change.station_id == station_id:
                price = change.price
        return price


def _has_operations(obj):
    return all(callable(getattr(obj, op, None)) for op in SERVER_OPERATIONS)


def _bind(server, send_price_update):
    """Connect the server side to the send port.

    ``server`` is either an object providing SERVER_OPERATIONS (a module or an
    instance; the send port is attached as attribute ``send_price_update``), or
    a class or factory that is called with the send port and returns such an object.
    """
    if isinstance(server, type) or (callable(server) and not _has_operations(server)):
        server = server(send_price_update)
    elif _has_operations(server):
        server.send_price_update = send_price_update
    if not _has_operations(server):
        raise TypeError("server must provide " + ", ".join(SERVER_OPERATIONS))
    return server


class Simulation:
    """Clients and transport around the server side, driven one logical second at a time.

    Each step to time t: deliver every message due by t; issue the central
    service's changes for t (GASV4PRDA-26) into the server; call the server's
    advance_time(t) (GASV4PRDA-24); deliver again, so zero-delay messages sent
    in this second arrive in it.
    """

    def __init__(
        self,
        seed,
        server,
        *,
        stations=3,
        prices=(10, 20, 30, 40, 50),
        horizon=300,
        change_rate=0.2,
        loss_rate=0.1,
        duplicate_rate=0.1,
        outages=True,
        up_range=(60, 240),
        down_range=(1, 40),
    ):
        if isinstance(stations, int):
            station_ids = [f"S{i}" for i in range(1, stations + 1)]
        else:
            station_ids = [str(sid) for sid in stations]
        if not station_ids or len(set(station_ids)) != len(station_ids):
            raise ValueError("station identifiers must be distinct and non-empty")
        for name, (low, high) in (("up_range", up_range), ("down_range", down_range)):
            if not 1 <= low <= high:
                raise ValueError(name + " needs 1 <= low <= high")

        self.seed = seed
        self.horizon = horizon
        self._now = 0
        self._loss_rate = loss_rate
        self._duplicate_rate = duplicate_rate
        self._transport_rng = random.Random(f"{seed}/transport")
        self._counter = itertools.count()
        self._queue: List[Tuple[int, int, Message]] = []  # heap of (due, order, message)
        self._last_ack_due = {sid: 0 for sid in station_ids}

        self.central = CentralService(
            random.Random(f"{seed}/central"), station_ids, prices, change_rate, horizon
        )
        self.stations: Dict[str, Station] = {
            sid: Station(
                sid,
                _Reachability(random.Random(f"{seed}/reach/{sid}"), outages, up_range, down_range),
            )
            for sid in station_ids
        }
        self.send_calls: List[SendCall] = []
        self.ack_calls: List[AckCall] = []
        self.messages: List[Message] = []

        self._server = _bind(server, self._send_price_update)

    @property
    def now(self):
        return self._now

    def in_flight(self):
        """Number of messages scheduled for delivery and not yet delivered or dropped."""
        return len(self._queue)

    def step(self):
        """Advance logical time by one second and run that second's events."""
        self._now += 1
        t = self._now
        self._deliver_due()
        for station_id, price in self.central.issue(t):
            self._server.desired_price_change(station_id, price)
        self._server.advance_time(t)
        self._deliver_due()
        return t

    def run(self, seconds):
        for _ in range(seconds):
            self.step()
        return self._now

    def run_until_idle(self, max_time=100_000):
        """Step until the central service has finished and nothing is in flight.

        Stops early at ``max_time``; check ``in_flight()`` to tell the cases apart.
        """
        while self._now < max_time and (self._now < self.horizon or self._queue):
            self.step()
        return self._now

    # Transport

    def _enqueue(self, msg):
        heapq.heappush(self._queue, (msg.due_at, next(self._counter), msg))

    def _deliver_due(self):
        t = self._now
        while self._queue and self._queue[0][0] <= t:
            _, _, msg = heapq.heappop(self._queue)
            if msg.kind == "update":
                self._deliver_update(msg, t)
            else:
                self._deliver_ack(msg, t)

    def _deliver_update(self, msg, t):
        station = self.stations[msg.station_id]
        msg.delivered_at = t
        if not station.reachable_at(t):
            msg.status = "dropped"
            return
        msg.status = "delivered"
        station.received.append((t, msg.sequence_number, msg.price))
        if msg.price != station.display:
            station.display_history.append((t, msg.price))
        self._send_ack(msg.station_id, msg.sequence_number, t)

    def _deliver_ack(self, msg, t):
        msg.status = "delivered"
        msg.delivered_at = t
        self.ack_calls.append(AckCall(t, msg.station_id, msg.sequence_number))
        self._server.acknowledgement_received(msg.station_id, msg.sequence_number)

    def _send_price_update(self, station_id, sequence_number, price):
        """Send port (GASV4PRDA-25): called by the server, outcome decided here."""
        t = self._now
        self.send_calls.append(SendCall(t, station_id, sequence_number, price))
        if not self.stations[station_id].reachable_at(t):
            msg = Message("update", station_id, sequence_number, price, t)
            msg.status = "dropped"
            self.messages.append(msg)
            return
        copies = [False]
        if self._transport_rng.random() < self._duplicate_rate:
            copies.append(True)
        for duplicate in copies:
            msg = Message("update", station_id, sequence_number, price, t, duplicate)
            self.messages.append(msg)
            if self._transport_rng.random() < self._loss_rate:
                msg.status = "lost"
                continue
            msg.due_at = t + self._transport_rng.randint(0, MAX_DELAY)
            self._enqueue(msg)

    def _send_ack(self, station_id, sequence_number, t):
        msg = Message("ack", station_id, sequence_number, None, t)
        self.messages.append(msg)
        if self._transport_rng.random() < self._loss_rate:
            msg.status = "lost"
            return
        # Acknowledgements from one station keep their order: never earlier than the previous one.
        due = max(t + self._transport_rng.randint(0, MAX_DELAY), self._last_ack_due[station_id])
        self._last_ack_due[station_id] = due
        msg.due_at = due
        self._enqueue(msg)


def _bind_check():
    return all(name in dir(Simulation) for name in ("step", "run_until_idle"))
