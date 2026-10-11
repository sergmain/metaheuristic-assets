'''Deterministic simulation of the environment around the server side (app).

Everything simulated here is the Environment: the price change source, the
transport to the stations, the stations, and the simulated pricing team. The
server side is reached only through the ports named in the Interface.

Inbound to the server (called by this package):
    server.set_desired_price(station_id, price)            GASV4ACCJ-19
    server.acknowledgement_received(station_id, send_id)   GASV4ACCJ-21
    server.simulated_time_wakeup(now)                      GASV4ACCJ-22

Outbound from the server (the server calls these on the ports object it is given):
    ports.send_price_update(station_id, price, send_id)     GASV4ACCJ-20
    ports.notify_pricing_team(station_id, price, ack_time)  GASV4ACCJ-50, returns (accepted, time)

The server argument of Simulation is either an object or module providing
set_desired_price (it receives the ports through connect(ports) when it has a
connect attribute), or a factory called as server(ports) returning such an object.

Time is whole simulated seconds. Each second the transport delivers every due
event, then calls simulated_time_wakeup, then delivers events that became due in
that second. Any wake-up requested at a whole second is therefore served.
'''

import heapq
import random
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

MAX_DELAY = 20
MAX_ACK_LATENCY = 10
MIN_REACHABLE_RUN = 120
MAX_UNREACHABLE_RUN = 200
REACHABILITY_TAIL = 3600

_CHANGE = 'change'
_DELIVER = 'deliver'
_ACK = 'ack'


@dataclass
class Delivery:
    time: int
    order: int
    send_id: Any
    price: int


@dataclass
class Station:
    station_id: str
    unreachable: List[Tuple[int, int]]
    applied_price: Optional[int] = None
    desired_history: List[Tuple[int, int]] = field(default_factory=list)
    # one entry per desired change: [change_time, price, converged_at or None]
    convergence: List[list] = field(default_factory=list)
    deliveries: List[Delivery] = field(default_factory=list)
    acks_emitted: List[Tuple[int, Any]] = field(default_factory=list)
    last_ack_at: int = 0

    def is_reachable(self, t: int) -> bool:
        return not any(start <= t < end for start, end in self.unreachable)


@dataclass
class Send:
    send_id: Any
    station_id: str
    price: int
    sent_at: int
    outcome: str = 'pending'  # 'unreachable' | 'lost' | 'delivered'
    delivery_at: Optional[int] = None
    ack_at: Optional[int] = None


@dataclass
class Change:
    time: int
    station_id: str
    price: int
    result: Any  # what set_desired_price returned


@dataclass
class Ack:
    time: int  # arrival at the server
    station_id: str
    send_id: Any
    order: int


@dataclass
class Notification:
    time: int  # when handed over and when the pricing team answered
    station_id: str
    price: int
    ack_time: int
    accepted: bool


def _next_price(rng, past):
    current = past[-1] if past else None
    earlier = [p for p in past if p != current]
    if earlier and rng.random() < 0.3:
        return rng.choice(earlier)  # change back to a previously held price
    while True:
        price = rng.randint(50, 150)
        if price != current:
            return price


def _change_schedule(rng, station_ids, horizon):
    changes = []
    history = {sid: [] for sid in station_ids}
    t = rng.randint(0, 30)
    while t < horizon:
        sid = rng.choice(station_ids)
        if rng.random() < 0.25:
            times = sorted(t + rng.randint(0, 55) for _ in range(rng.randint(2, 4)))
        else:
            times = [t]
        for when in times:
            price = _next_price(rng, history[sid])
            history[sid].append(price)
            changes.append((when, sid, price))
        t = times[-1] + rng.randint(5, 90)
    return changes


def _unreachable_intervals(rng, until):
    # Reachable runs are at least MIN_REACHABLE_RUN long and unreachable
    # intervals at most MAX_UNREACHABLE_RUN, so every 600 s window holds at
    # least 120 s of reachability.
    intervals = []
    pos = 0
    while pos < until:
        pos += rng.randint(MIN_REACHABLE_RUN, 600)
        if rng.random() < 0.5:
            length = rng.randint(10, MAX_UNREACHABLE_RUN)
            intervals.append((pos, pos + length))
            pos += length
    return intervals


def _resolve_server(server, ports):
    if hasattr(server, 'set_desired_price'):
        connect = getattr(server, 'connect', None)
        if connect is not None:
            connect(ports)
        return server
    if callable(server):
        return server(ports)
    raise TypeError('server must provide set_desired_price or be a factory taking the ports')


class _Ports:
    def __init__(self, sim):
        self._sim = sim

    def send_price_update(self, station_id, price, send_id):
        self._sim._send(station_id, price, send_id)

    def notify_pricing_team(self, station_id, price, ack_time):
        return self._sim._notify(station_id, price, ack_time)


class Simulation:
    def __init__(self, seed, server: Any, station_ids: Sequence[str] = ('S1', 'S2', 'S3'),
                 horizon: int = 1200, loss_rate: float = 0.1, pricing_fault_rate: float = 0.0):
        self.seed = seed
        self.horizon = horizon
        self.loss_rate = loss_rate
        self.pricing_fault_rate = pricing_fault_rate
        self.now = 0
        self._next_second = 0
        self._heap: List[tuple] = []
        self._seq = 0
        self._rng = random.Random(seed)
        ids = list(station_ids)
        schedule = _change_schedule(self._rng, ids, horizon)
        self.stations = {
            sid: Station(sid, _unreachable_intervals(self._rng, horizon + REACHABILITY_TAIL))
            for sid in ids
        }
        self.sends: List[Send] = []
        self.changes: List[Change] = []
        self.acks: List[Ack] = []
        self.notifications: List[Notification] = []
        self.ports = _Ports(self)
        self.server = _resolve_server(server, self.ports)
        for when, sid, price in schedule:
            self._push(when, _CHANGE, (sid, price))

    # ----- observation -------------------------------------------------

    def in_flight(self) -> int:
        '''Number of sends not yet delivered plus acknowledgements not yet arrived.'''
        return sum(1 for entry in self._heap if entry[2] != _CHANGE)

    def pending_changes(self) -> int:
        return sum(1 for entry in self._heap if entry[2] == _CHANGE)

    def desired_price(self, station_id):
        history = self.stations[station_id].desired_history
        return history[-1][1] if history else None

    def applied_price(self, station_id):
        return self.stations[station_id].applied_price

    def convergence(self, station_id):
        '''(change_time, price, converged_at) per desired change; converged_at None if never reached.'''
        return [tuple(entry) for entry in self.stations[station_id].convergence]

    def is_reachable(self, station_id, t):
        return self.stations[station_id].is_reachable(t)

    def unreachable_intervals(self, station_id):
        return list(self.stations[station_id].unreachable)

    # ----- driving -----------------------------------------------------

    def step(self) -> int:
        '''Advance simulated time by one second; return that second.'''
        second = self._next_second
        self._next_second += 1
        self.now = second
        self._drain(second)
        self.server.simulated_time_wakeup(second)
        self._drain(second)
        return second

    def advance_to(self, t: int) -> None:
        while self._next_second <= t:
            self.step()

    def run_until_idle(self, limit: Optional[int] = None) -> int:
        '''Step until no send or acknowledgement is in flight and no change is pending.'''
        limit = self.horizon + REACHABILITY_TAIL if limit is None else limit
        while self.in_flight() or self.pending_changes():
            if self._next_second > limit:
                raise RuntimeError('simulation not idle by second %d' % limit)
            self.step()
        return self.now

    # ----- internals ---------------------------------------------------

    def _push(self, time, kind, payload):
        self._seq += 1
        heapq.heappush(self._heap, (time, self._seq, kind, payload))

    def _drain(self, second):
        while self._heap and self._heap[0][0] <= second:
            _, _, kind, payload = heapq.heappop(self._heap)
            self._dispatch(kind, payload)

    def _dispatch(self, kind, payload):
        if kind == _CHANGE:
            sid, price = payload
            st = self.stations[sid]
            st.desired_history.append((self.now, price))
            st.convergence.append([self.now, price, self.now if st.applied_price == price else None])
            result = self.server.set_desired_price(sid, price)
            self.changes.append(Change(self.now, sid, price, result))
        elif kind == _DELIVER:
            send = payload
            st = self.stations[send.station_id]
            st.deliveries.append(Delivery(self.now, len(st.deliveries), send.send_id, send.price))
            st.applied_price = send.price
            st.acks_emitted.append((self.now, send.send_id))
            last = st.convergence[-1] if st.convergence else None
            if last is not None and last[2] is None and last[1] == send.price:
                last[2] = self.now
        else:
            send = payload
            self.acks.append(Ack(self.now, send.station_id, send.send_id, len(self.acks)))
            self.server.acknowledgement_received(send.station_id, send.send_id)

    def _send(self, station_id, price, send_id):
        station = self.stations[station_id]
        record = Send(send_id, station_id, price, self.now)
        self.sends.append(record)
        if not station.is_reachable(self.now):
            record.outcome = 'unreachable'
            return
        if self._rng.random() < self.loss_rate:
            record.outcome = 'lost'
            return
        delivery_at = self.now + self._rng.randint(0, MAX_DELAY)
        # Acknowledgements return in send order: never earlier than the previous one.
        ack_at = max(delivery_at + self._rng.randint(0, MAX_ACK_LATENCY), station.last_ack_at)
        station.last_ack_at = ack_at
        record.outcome = 'delivered'
        record.delivery_at = delivery_at
        record.ack_at = ack_at
        self._push(delivery_at, _DELIVER, record)
        self._push(ack_at, _ACK, record)

    def _notify(self, station_id, price, ack_time):
        accepted = not (self.pricing_fault_rate > 0 and self._rng.random() < self.pricing_fault_rate)
        self.notifications.append(Notification(self.now, station_id, price, ack_time, accepted))
        return accepted, self.now
