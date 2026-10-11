"""Deterministic simulation of the environment around the server side `app`.

Logical time is a float in minutes. Events sit in a heap ordered by
(time, priority, insertion order), so equal-time events run in a fixed order:
reachability transitions, then price-source calls, then deliveries, then acks.
"""
import heapq
import random
from dataclasses import dataclass
from typing import Any, Callable, Optional

PRICES = (100, 105, 110, 115, 120, 125)
UPDATE_DELAY = (0.0, 2.0)  # logical minutes, drawn per update
ACK_DELAY = (0.0, 1.0)     # logical minutes, drawn per acknowledgement

_REACH, _SET, _DELIVER, _ACK = 0, 1, 2, 3


@dataclass
class Record:
    """One observed event. kind: set, dispatch, deliver, display, ack, reach.

    detail: for set, the value returned by app; for reach, the reachable flag.
    """
    time: float
    kind: str
    station: Any
    seq: Optional[int] = None
    price: Any = None
    detail: Any = None


class Station:
    """Fixed station model: display is the price of the last update received."""

    def __init__(self, station_id):
        self.station_id = station_id
        self.display = None  # nothing shown before the first receipt
        self.reachable = True


def _price_schedule(rng, station_ids, stop_time):
    schedule = []
    t = 0.0
    while True:
        t += rng.uniform(0.1, 3.0)
        if t >= stop_time:
            break
        if rng.random() < 0.4:
            # burst: several changes to one station, spaced inside the delay bound
            station = rng.choice(station_ids)
            tb = t
            for _ in range(rng.randint(2, 4)):
                if tb >= stop_time:
                    break
                schedule.append((tb, station, rng.choice(PRICES)))
                tb += rng.uniform(0.05, 0.5)
            t = tb
        else:
            schedule.append((t, rng.choice(station_ids), rng.choice(PRICES)))
    return schedule


def _reach_schedule(rng, horizon):
    changes = []
    t = 0.0
    state = True
    while True:
        t += rng.uniform(1.0, 6.0) if state else rng.uniform(0.5, 4.0)
        if t > horizon:
            break
        state = not state
        changes.append((t, state))
    return changes


class Simulation:
    """Simulated clients and transport around the server side.

    server_factory is called once with the outbound DispatchUpdate port
    (station_id, sequence, price) and must return the server side object (or
    module) providing set_desired_price, acknowledgement_received and
    reachability_changed. It is stored as self.app.
    """

    def __init__(self, seed, server_factory: Callable[[Callable[[Any, int, Any], None]], Any],
                 stations=3, stop_time=30.0, horizon=None):
        if stations < 1:
            raise ValueError('need at least one station')
        self.seed = seed
        self.now = 0.0
        self.stop_time = float(stop_time)
        self.horizon = self.stop_time + 20.0 if horizon is None else float(horizon)
        self.station_ids = tuple('station-%d' % i for i in range(1, stations + 1))
        self.stations = {sid: Station(sid) for sid in self.station_ids}
        self.trace = []
        self.reach_schedule = {}
        self._rng = random.Random(seed)
        self._queue = []
        self._counter = 0
        self._held = {sid: [] for sid in self.station_ids}
        self._last_ack = {sid: 0.0 for sid in self.station_ids}
        self.price_schedule = _price_schedule(self._rng, self.station_ids, self.stop_time)
        for t, sid, price in self.price_schedule:
            self._push(t, _SET, ('set', sid, price))
        for sid in self.station_ids:
            changes = _reach_schedule(self._rng, self.horizon)
            self.reach_schedule[sid] = changes
            for t, value in changes:
                self._push(t, _REACH, ('reach', sid, value))
        self.app = server_factory(self.dispatch_update)

    def _push(self, time, priority, payload):
        heapq.heappush(self._queue, (time, priority, self._counter, payload))
        self._counter += 1

    def dispatch_update(self, station_id, sequence, price):
        """Outbound port DispatchUpdate: the server sends one update to a station."""
        if station_id not in self.stations:
            raise KeyError('unknown station %r' % (station_id,))
        self.trace.append(Record(self.now, 'dispatch', station_id, sequence, price))
        delay = self._rng.uniform(*UPDATE_DELAY)
        self._push(self.now + delay, _DELIVER, ('deliver', station_id, sequence, price))

    @property
    def convergence_start(self):
        """Logical time of the last SetDesiredPrice call, or None if there are none."""
        return self.price_schedule[-1][0] if self.price_schedule else None

    @property
    def quiescent(self):
        """True when no event remains scheduled."""
        return not self._queue

    def in_flight(self):
        """Updates not yet delivered (including held) plus acknowledgements not yet returned."""
        updates = sum(1 for e in self._queue if e[3][0] in ('deliver', 'ack'))
        return updates + sum(len(h) for h in self._held.values())

    def traffic(self, kind):
        return [r for r in self.trace if r.kind == kind]

    def step(self):
        """Process the next event. Returns False when nothing is scheduled."""
        if not self._queue:
            return False
        time, _, _, payload = heapq.heappop(self._queue)
        self.now = time
        kind = payload[0]
        if kind == 'set':
            _, sid, price = payload
            rec = Record(self.now, 'set', sid, price=price)
            self.trace.append(rec)
            rec.detail = self.app.set_desired_price(sid, price)
        elif kind == 'deliver':
            _, sid, seq, price = payload
            st = self.stations[sid]
            if not st.reachable:
                self._held[sid].append((seq, price))
            else:
                self.trace.append(Record(self.now, 'deliver', sid, seq, price))
                st.display = price
                self.trace.append(Record(self.now, 'display', sid, seq, price))
                ack_time = max(self.now + self._rng.uniform(*ACK_DELAY), self._last_ack[sid])
                self._last_ack[sid] = ack_time
                self._push(ack_time, _ACK, ('ack', sid, seq, price))
        elif kind == 'ack':
            _, sid, seq, price = payload
            self.trace.append(Record(self.now, 'ack', sid, seq, price))
            self.app.acknowledgement_received(sid, seq, price)
        else:
            _, sid, value = payload
            st = self.stations[sid]
            if st.reachable != value:
                st.reachable = value
                self.trace.append(Record(self.now, 'reach', sid, detail=value))
                self.app.reachability_changed(sid, value)
                if value:
                    for seq, price in self._held[sid]:
                        delay = self._rng.uniform(*UPDATE_DELAY)
                        self._push(self.now + delay, _DELIVER, ('deliver', sid, seq, price))
                    self._held[sid] = []
        return True

    def run_until(self, t):
        """Process every event with time <= t, then set the clock to t."""
        while self._queue and self._queue[0][0] <= t:
            self.step()
        self.now = max(self.now, t)
        return self.now

    def run(self, max_events=1000000):
        """Process events until nothing is in flight or scheduled."""
        n = 0
        while self.step():
            n += 1
            if n > max_events:
                raise RuntimeError('more than %d events; server may dispatch without end' % max_events)
        return self.now

    def force_reachable(self, station_id, from_time):
        """Make station_id reachable from from_time onward, dropping later unreachable transitions."""
        if from_time < self.now:
            raise ValueError('cannot force reachability in the past')
        self._queue = [e for e in self._queue
                       if not (e[3][0] == 'reach' and e[3][1] == station_id and e[0] >= from_time)]
        heapq.heapify(self._queue)
        self._push(from_time, _REACH, ('reach', station_id, True))
        kept = [c for c in self.reach_schedule[station_id] if c[0] < from_time]
        self.reach_schedule[station_id] = kept + [(from_time, True)]
