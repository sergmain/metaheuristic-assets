'''Deterministic simulated environment: station clients, transport and source.

No threads, clocks or real I/O. Time is the logical tick counter, and all
randomness comes from one random.Random(seed) built from the test's seed.
'''
import random
from dataclasses import dataclass
from typing import Any, Optional

__all__ = ['Simulation', 'Station', 'ChangeRecord', 'SendRecord', 'AckRecord',
           'QueryRecord', 'ConvergenceReport']


class Station:
    '''Holds exactly one displayed price, initially None (unset). Never configured.'''

    def __init__(self, station_id):
        self.station_id = station_id
        self.displayed = None

    def apply(self, price):
        self.displayed = price
        return self.displayed


@dataclass
class ChangeRecord:
    tick: int
    station: str
    price: Any
    result: Any  # what I1 returned (the accepted desired version)


@dataclass
class SendRecord:
    tick: int
    station: str
    price: Any
    version: Any
    lost: bool = False
    deliver_at: Optional[int] = None
    delivered_tick: Optional[int] = None


@dataclass
class AckRecord:
    emitted_tick: int
    station: str
    version: Any
    displayed: Any
    deliver_at: int = 0
    delivered_tick: Optional[int] = None


@dataclass
class QueryRecord:
    tick: int
    station: str
    result: Any  # what I3 returned


@dataclass
class ConvergenceReport:
    tick: int
    precondition: bool
    stations: dict
    failures: list

    @property
    def converged(self):
        return self.precondition and not self.failures


def _field(status, *names):
    for name in names:
        if isinstance(status, dict) and name in status:
            return status[name]
        if hasattr(status, name):
            return getattr(status, name)
    raise KeyError('status has none of {}'.format(names))


class Simulation:
    '''Clients, transport and central source for one seeded run.

    Usage: sim = Simulation(seed); sim.attach(lambda send: app.Server(send_update=send));
    then sim.step() / sim.run_until_idle() / sim.converge().

    The server object given by the factory must expose accept_desired_price(station, price),
    query_station_status(station), receive_acknowledgement(station, version, displayed_price)
    and tick(). The factory receives sim.send_update, the outbound port I2.
    '''

    def __init__(self, seed, stations=('s1', 's2', 's3'), stop_tick=20,
                 fault_window=(1, 10), max_delay=3, loss=0.3,
                 change_rate=0.3, max_changes_per_tick=3, price_range=(1, 1000)):
        start, end = fault_window
        if max_delay < 1:
            raise ValueError('max_delay must be at least 1 tick')
        if not 0 <= start <= end:
            raise ValueError('fault_window must be (start, end) with 0 <= start <= end')
        self.seed = seed
        self.rng = random.Random(seed)
        self.station_ids = tuple(stations)
        self.stations = {sid: Station(sid) for sid in self.station_ids}
        self.stop_tick = stop_tick
        self.fault_start, self.fault_end = start, end
        self.max_delay = max_delay
        self.loss = loss
        self.now = 0
        self.server = None
        self.source_schedule = self._draw_source_schedule(change_rate, max_changes_per_tick, price_range)
        self.outages = self._draw_outages()
        self.manual_reachable = {}
        self.changes = []   # ChangeRecord, one per I1 call
        self.sends = []     # SendRecord, one per I2 call (lost ones flagged)
        self.acks = []      # AckRecord, in delivery order to the server (I4)
        self.queries = []   # QueryRecord, one per station per tick (I3)
        self._updates_in_flight = []
        self._acks_in_flight = {sid: [] for sid in self.station_ids}
        self._last_ack_due = {sid: 0 for sid in self.station_ids}

    def _draw_source_schedule(self, change_rate, max_changes, price_range):
        lo, hi = price_range
        schedule = {}
        for tick in range(1, self.stop_tick + 1):
            for sid in self.station_ids:
                if self.rng.random() < change_rate:
                    for _ in range(self.rng.randint(1, max_changes)):
                        schedule.setdefault(tick, []).append((sid, self.rng.randint(lo, hi)))
        return schedule

    def _draw_outages(self):
        outages = {}
        for sid in self.station_ids:
            windows = []
            count = self.rng.randint(0, 2)
            if self.fault_end > self.fault_start:
                for _ in range(count):
                    start = self.rng.randrange(self.fault_start, self.fault_end)
                    length = self.rng.randint(1, 4)
                    windows.append((start, min(start + length, self.fault_end)))
            outages[sid] = windows
        return outages

    def attach(self, server_factory):
        '''Build the server: server_factory(send_update) returns the app object.'''
        self.server = server_factory(self.send_update)
        return self.server

    def set_reachable(self, station, flag):
        '''Suspend (False) or resume (True) delivery both ways; None clears the override.'''
        if flag is None:
            self.manual_reachable.pop(station, None)
        else:
            self.manual_reachable[station] = bool(flag)

    def reachable(self, station, tick=None):
        if station in self.manual_reachable:
            return self.manual_reachable[station]
        t = self.now if tick is None else tick
        return not any(a <= t < b for a, b in self.outages[station])

    def send_update(self, station, price, version):
        '''Port I2 (outbound from the server). Returns None: no acknowledgement.'''
        if station not in self.stations:
            raise KeyError(station)
        rec = SendRecord(self.now, station, price, version)
        self.sends.append(rec)
        if self.fault_start <= self.now < self.fault_end and self.rng.random() < self.loss:
            rec.lost = True
            return None
        rec.deliver_at = self.now + self.rng.randint(1, self.max_delay)
        self._updates_in_flight.append(rec)
        return None

    def step(self):
        '''Advance one tick: source changes (I1), server tick (I4), deliveries, then queries (I3).'''
        if self.server is None:
            raise RuntimeError('attach a server before stepping')
        self.now += 1
        t = self.now
        for sid, price in self.source_schedule.get(t, []):
            result = self.server.accept_desired_price(sid, price)
            self.changes.append(ChangeRecord(t, sid, price, result))
        self.server.tick()
        self._deliver_updates(t)
        self._deliver_acks(t)
        for sid in self.station_ids:
            self.queries.append(QueryRecord(t, sid, self.server.query_station_status(sid)))
        return t

    def _deliver_updates(self, t):
        due = [u for u in self._updates_in_flight
               if u.deliver_at <= t and self.reachable(u.station, t)]
        due_ids = {id(u) for u in due}
        self._updates_in_flight = [u for u in self._updates_in_flight if id(u) not in due_ids]
        due.sort(key=lambda u: u.deliver_at)  # stable: ties keep send order
        for u in due:
            u.delivered_tick = t
            displayed = self.stations[u.station].apply(u.price)
            self._emit_ack(t, u.station, u.version, displayed)

    def _emit_ack(self, t, sid, version, displayed):
        due = max(t + self.rng.randint(1, self.max_delay), self._last_ack_due[sid])
        self._last_ack_due[sid] = due
        self._acks_in_flight[sid].append(AckRecord(t, sid, version, displayed, due))

    def _deliver_acks(self, t):
        for sid in self.station_ids:
            queue = self._acks_in_flight[sid]
            while queue and queue[0].deliver_at <= t and self.reachable(sid, t):
                ack = queue.pop(0)
                ack.delivered_tick = t
                self.acks.append(ack)
                self.server.receive_acknowledgement(sid, ack.version, ack.displayed)

    def in_flight_updates(self):
        return list(self._updates_in_flight)

    def in_flight_acks(self):
        return [a for sid in self.station_ids for a in self._acks_in_flight[sid]]

    def in_flight(self):
        return bool(self._updates_in_flight) or bool(self.in_flight_acks())

    def run(self, ticks):
        for _ in range(ticks):
            self.step()
        return self.now

    def run_until_idle(self, max_ticks=10000):
        '''Step until nothing is in flight and the source has stopped (now >= stop_tick).'''
        for _ in range(max_ticks):
            self.step()
            if self.now >= self.stop_tick and not self.in_flight():
                return self.now
        raise RuntimeError('transport still busy after {} ticks'.format(max_ticks))

    @property
    def settle_tick(self):
        '''Tick after which every fault has closed and every bounded delivery has passed.'''
        return max(self.stop_tick, self.fault_end) + 2 * self.max_delay + 1

    @property
    def budget_tick(self):
        '''Fixed tick budget for convergence, derived from the configuration.'''
        return self.settle_tick + 20 * (self.max_delay + 1)

    def latest_desired(self):
        latest = {}
        for c in self.changes:
            latest[c.station] = c.price
        return latest

    def check(self):
        '''Compare displayed prices with the latest desired prices and the I3 up-to-date flag.

        Queries the server directly and does not add to self.queries.
        '''
        desired = self.latest_desired()
        precondition = (self.now >= self.stop_tick and self.now >= self.fault_end
                        and all(self.reachable(sid) for sid in self.station_ids))
        failures = []
        if not precondition:
            failures.append('source stop, fault window close or reachability not yet met')
        stations = {}
        for sid in self.station_ids:
            status = self.server.query_station_status(sid)
            up = _field(status, 'up_to_date', 'up_to_date_flag', 'is_up_to_date')
            shown = self.stations[sid].displayed
            want = desired.get(sid)
            stations[sid] = {'displayed': shown, 'desired': want, 'up_to_date': up}
            if want is not None and shown != want:
                failures.append('{}: displayed {!r} != desired {!r}'.format(sid, shown, want))
            if not up:
                failures.append('{}: up-to-date flag is false'.format(sid))
        return ConvergenceReport(self.now, precondition, stations, failures)

    def converge(self):
        '''Run ticks until settled and converged, or until the budget; returns the final report.'''
        report = self.check()
        while self.now < self.budget_tick:
            if self.now >= self.settle_tick and report.converged:
                break
            self.step()
            report = self.check()
        return report

    def assert_converged(self):
        report = self.converge()
        if not report.converged:
            raise AssertionError('not converged at tick {}: {}'.format(report.tick, report.failures))
        return report
