'''Deterministic simulation of the environment of the price-update server.

The environment is the central price source, the stations and the transport
between them and the server. Nothing here uses threads, clocks or real I/O.

Server contract (the server side must provide these; names are fixed here):
    server.set_desired_price(station_id, price)             GASV4E2CL-18
    server.acknowledgement_received(station_id, update_id)  GASV4E2CL-20
    server.observe_station(station_id) -> view with desired_price (attribute or key)  GASV4E2CL-21
The server calls send_price_update(station_id, update_id, price)  GASV4E2CL-19,
which the simulation provides.

Usage:
    sim = Simulation(seed, server_factory)   # server_factory(send_price_update) -> server
    sim.run_until_idle()                     # or step() / run_until(t)
    assert not price_at_send_violations(sim)
'''
import heapq
import random
from collections.abc import Mapping
from dataclasses import dataclass

STATIONS = ('S1', 'S2', 'S3')
DURATION = 6 * 3600        # virtual seconds of central price changes
MAX_DELAY = 60             # transport delay bound, virtual seconds
SETTLE_SECONDS = 300       # convergence window, virtual seconds

_PRICE = 'price'
_UPDATE = 'update'
_ACK = 'ack'


@dataclass
class Change:
    time: int
    station: str
    value: object
    result: object


@dataclass
class SendRecord:
    time: int
    station: str
    update_id: int
    price: object
    desired_at_send: object
    outstanding_before: tuple


@dataclass
class Message:
    kind: str              # 'update' (to station) or 'ack' (from station)
    station: str
    sent_at: int
    update_id: int
    price: object = None
    delivered_at: object = None


class Station:
    '''Fixed station model: shows the last price delivered, in arrival order.'''

    def __init__(self, station_id):
        self.station_id = station_id
        self.displayed_price = None
        self.received = []     # (update_id, price) in arrival order

    def deliver_update(self, update_id, price):
        self.displayed_price = price
        self.received.append((update_id, price))


def _field(view, name):
    if isinstance(view, Mapping):
        return view[name]
    return getattr(view, name)


class Simulation:
    def __init__(self, seed, server_factory, stations=STATIONS, duration=DURATION):
        self.seed = seed
        self.now = 0
        self.stations = {sid: Station(sid) for sid in stations}
        self.changes = []
        self.sends = []
        self.to_station = []
        self.from_station = []
        self._queue = []
        self._seq = 0
        self._rng_price = random.Random(f'{seed}/price')
        self._rng_net = random.Random(f'{seed}/net')
        self._rng_outage = random.Random(f'{seed}/outage')
        self._windows = {sid: [] for sid in stations}
        self._window_cursor = {sid: 0 for sid in stations}
        self._unacked = {sid: [] for sid in stations}
        self._last_ack_due = {sid: 0 for sid in stations}
        if callable(server_factory) and not hasattr(server_factory, 'set_desired_price'):
            self.server = server_factory(self.send_price_update)
        else:
            self.server = server_factory
        self._schedule_price_changes(duration)

    # ---- central price source (GASV4E2CL-22) ----

    def _schedule_price_changes(self, duration):
        rng = self._rng_price
        stations = list(self.stations)
        history = {sid: [] for sid in stations}
        t = 0
        while True:
            t += rng.randint(120, 1200)          # quiet period, sometimes long enough to settle
            if t >= duration:
                break
            sid = rng.choice(stations)
            for _ in range(rng.choice((1, 1, 2, 3, 4))):   # burst within one transport delay
                t += rng.randint(1, 15)
                value = self._next_value(rng, history[sid])
                history[sid].append(value)
                self._push(t, _PRICE, (sid, value))

    @staticmethod
    def _next_value(rng, history):
        if len(history) >= 2 and rng.random() < 0.3:
            return history[-2]                   # reversion to an earlier value
        return rng.randint(1, 999)

    # ---- port GASV4E2CL-19, provided to the server ----

    def send_price_update(self, station_id, update_id, price):
        desired = self.desired_price(station_id)
        outstanding = tuple(self._unacked[station_id])
        self._unacked[station_id].append(update_id)
        self.sends.append(SendRecord(self.now, station_id, update_id, price, desired, outstanding))
        msg = Message('update', station_id, self.now, update_id, price)
        self.to_station.append(msg)
        self._enqueue(_UPDATE, msg, self.now + self._rng_net.randint(0, MAX_DELAY))

    # ---- driving ----

    def step(self):
        '''Process the next scheduled event. Returns False when none is scheduled.'''
        if not self._queue:
            return False
        time, _, kind, payload = heapq.heappop(self._queue)
        self.now = time
        if kind == _PRICE:
            station_id, value = payload
            result = self.server.set_desired_price(station_id, value)
            self.changes.append(Change(time, station_id, value, result))
        elif kind == _UPDATE:
            self._deliver_update(payload)
        else:
            self._deliver_ack(payload)
        return True

    def run_until(self, time):
        while self._queue and self._queue[0][0] <= time:
            self.step()
        for sid in self.stations:
            self._extend_windows(sid, time)
        self.now = max(self.now, time)

    def run_until_idle(self):
        while self.step():
            pass
        return self.now

    def in_flight(self):
        '''Number of messages to or from stations not yet delivered.'''
        return sum(1 for entry in self._queue if entry[2] != _PRICE)

    def idle(self):
        '''True when no event at all (messages or scheduled changes) remains.'''
        return not self._queue

    def desired_price(self, station_id):
        return _field(self.server.observe_station(station_id), 'desired_price')

    def reachable(self, station_id, time=None):
        time = self.now if time is None else time
        self._extend_windows(station_id, time)
        return not any(start <= time < end for start, end in self._windows[station_id])

    def outages(self, station_id, until=None):
        '''Outage windows (start, end) of a station, generated up to until (default now).'''
        self._extend_windows(station_id, self.now if until is None else until)
        return list(self._windows[station_id])

    # ---- transport (GASV4E2CL-24) ----

    def _enqueue(self, kind, msg, due):
        self._push(self._arrival(msg.station, due), kind, msg)

    def _push(self, time, kind, payload):
        self._seq += 1
        heapq.heappush(self._queue, (time, self._seq, kind, payload))

    def _arrival(self, station_id, due):
        # A message due while the station is unreachable is held until the outage ends.
        self._extend_windows(station_id, due)
        for start, end in self._windows[station_id]:
            if start <= due < end:
                return end
        return due

    def _extend_windows(self, station_id, until):
        rng = self._rng_outage
        while self._window_cursor[station_id] <= until:
            start = self._window_cursor[station_id] + rng.randint(900, 7200)
            end = start + rng.randint(30, 900)
            self._windows[station_id].append((start, end))
            self._window_cursor[station_id] = end

    def _deliver_update(self, msg):
        msg.delivered_at = self.now
        self.stations[msg.station].deliver_update(msg.update_id, msg.price)
        ack = Message('ack', msg.station, self.now, msg.update_id)
        self.from_station.append(ack)
        due = max(self.now + self._rng_net.randint(0, MAX_DELAY), self._last_ack_due[msg.station])
        self._last_ack_due[msg.station] = due     # acknowledgements keep the station's order
        self._enqueue(_ACK, ack, due)

    def _deliver_ack(self, ack):
        ack.delivered_at = self.now
        pending = self._unacked[ack.station]
        if ack.update_id in pending:
            pending.remove(ack.update_id)
        self.server.acknowledgement_received(ack.station, ack.update_id)


# ---- oracles (GASV4E2CL-26..29, 25); each returns a list of violation strings ----

def price_at_send_violations(sim):
    return [
        f'update {s.update_id} to {s.station} at t={s.time} carried {s.price}, desired {s.desired_at_send}'
        for s in sim.sends if s.price != s.desired_at_send
    ]


def repeat_violations(sim):
    out = []
    previous = {}
    for s in sim.sends:
        prev = previous.get(s.station)
        if prev is not None and prev.price == s.price:
            out.append(f'update {s.update_id} to {s.station} repeats price {s.price}')
        if s.outstanding_before:
            out.append(f'update {s.update_id} to {s.station} sent while {list(s.outstanding_before)} unacknowledged')
        previous[s.station] = s
    return out


def unsent_change_violations(sim, until=None):
    until = sim.now if until is None else until
    out = []
    for i, change in enumerate(sim.changes):
        if change.time > until:
            continue
        later = [d for d in sim.changes[i + 1:] if d.station == change.station]
        sends = [s for s in sim.sends if s.station == change.station]
        after = [s for s in sends if s.time >= change.time]
        horizon = after[0].time if after else float('inf')
        if any(d.time < horizon for d in later):
            continue                              # superseded before any send: exempt
        values = [change.value] + [d.value for d in later]
        before = [s for s in sends if s.time < change.time]
        if before and before[-1].price == change.value:
            continue                              # already carried by an earlier send
        if any(s.price in values and s.time <= until for s in after):
            continue
        out.append(f'change {change.value} to {change.station} at t={change.time} never sent by t={until}')
    return out


def message_form_violations(sim):
    out = []
    for m in sim.to_station:
        if m.kind != 'update':
            out.append(f'to {m.station}: message kind {m.kind}')
    for m in sim.from_station:
        if m.kind != 'ack':
            out.append(f'from {m.station}: message kind {m.kind}')
    return out


def convergence_violations(sim):
    '''A station reachable and unchanged for SETTLE_SECONDS must display its desired price now.'''
    out = []
    for sid, station in sim.stations.items():
        if not sim.reachable(sid):
            continue
        last_change = max((c.time for c in sim.changes if c.station == sid), default=0)
        last_outage_end = max((end for _, end in sim.outages(sid) if end <= sim.now), default=0)
        settled_from = max(last_change, last_outage_end)
        if sim.now - settled_from < SETTLE_SECONDS:
            continue
        desired = sim.desired_price(sid)
        if station.displayed_price != desired:
            out.append(f'{sid} at t={sim.now} shows {station.displayed_price}, desired {desired}')
    return out
