"""Simulated environment: pricing team, reordering transport, dumb stations."""
import random
from dataclasses import dataclass


@dataclass
class SendRecord:
    event_index: int
    time: int
    station_id: object
    price: object
    send_id: object


@dataclass
class DeliveryRecord:
    event_index: int
    time: int
    station_id: object
    price: object
    send_id: object


@dataclass
class AckRecord:
    event_index: int
    time: int
    station_id: object
    send_id: object
    reported_price: object


@dataclass
class SubmitRecord:
    event_index: int
    time: int
    station_id: object
    price: object
    result: object


class Simulation:
    """Drive `app` step by step.

    Pricing team: submit() / schedule_submit().
    Transport: sends are in flight until delivered; delivery order is scripted
    (set_delivery_order) or else chosen with the seeded RNG (reordering).
    Stations: apply every received price as is (no version check, no dedup);
    each delivery produces one acknowledgement carrying the station's price.
    Acknowledgements are returned to app in the order they were produced.
    """

    def __init__(self, seed=0, station_ids=(), initial_price=None):
        self.rng = random.Random(seed)
        self.seed = seed
        self._counter = 0
        self._time = 0
        self.app = None
        self.station_prices = {s: initial_price for s in station_ids}
        self.sends = []
        self.deliveries = []
        self.acknowledgements = []
        self.submissions = []
        self._in_flight = []  # list of SendRecord
        self._ack_queue = []  # list of AckRecord-like tuples (station, send_id, price)
        self._orders = {}  # station_id -> list of send_ids in scripted order
        self._schedule = []  # (step, seq, station, price)
        self._steps = 0
        self._sched_seq = 0

    # ---- wiring -------------------------------------------------------
    def connect(self, app):
        def send_to_station(station_id, price, send_id):
            self._next()
            rec = SendRecord(self._counter, self._time, station_id, price, send_id)
            self.sends.append(rec)
            self._in_flight.append(rec)
            self.station_prices.setdefault(station_id, None)

        def current_time():
            return self._time

        self.app = app
        hook = getattr(app, "connect", None)
        if callable(hook):
            hook(send_to_station=send_to_station, current_time=current_time)
        else:
            app.send_to_station = send_to_station
            app.current_time = current_time
        return self

    def _next(self):
        self._counter += 1
        return self._counter

    # ---- clock --------------------------------------------------------
    @property
    def now(self):
        return self._time

    def advance_time(self, dt=1):
        self._time += dt

    # ---- pricing team -------------------------------------------------
    def submit(self, station_id, price):
        result = self.app.submit_desired_price(station_id, price)
        self.submissions.append(SubmitRecord(self._next(), self._time, station_id, price, result))
        return result

    def schedule_submit(self, after_steps, station_id, price):
        """Submit once `after_steps` transport steps have been taken (or when idle)."""
        self._sched_seq += 1
        self._schedule.append((after_steps, self._sched_seq, station_id, price))
        self._schedule.sort(key=lambda t: (t[0], t[1]))

    # ---- transport ----------------------------------------------------
    def set_delivery_order(self, station_id, send_ids):
        """Script the order in which sends to a station are delivered."""
        self._orders[station_id] = list(send_ids)

    @property
    def in_flight(self):
        return list(self._in_flight)

    @property
    def pending_acks(self):
        return list(self._ack_queue)

    def _pick(self):
        for sid, order in self._orders.items():
            for send_id in order:
                for rec in self._in_flight:
                    if rec.station_id == sid and rec.send_id == send_id:
                        return rec
        # scripted-but-not-yet-sent ids are skipped; unscripted use the RNG
        free = [r for r in self._in_flight
                if r.send_id not in self._orders.get(r.station_id, ())]
        if free:
            return self.rng.choice(free)
        return None

    def deliver(self, send_id, station_id=None):
        for rec in self._in_flight:
            if rec.send_id == send_id and (station_id is None or rec.station_id == station_id):
                return self._deliver(rec)
        raise KeyError(send_id)

    def _deliver(self, rec):
        self._in_flight.remove(rec)
        self._time += 1
        self.station_prices[rec.station_id] = rec.price
        d = DeliveryRecord(self._next(), self._time, rec.station_id, rec.price, rec.send_id)
        self.deliveries.append(d)
        self._ack_queue.append((rec.station_id, rec.send_id, rec.price))
        return d

    def deliver_ack(self):
        station_id, send_id, price = self._ack_queue.pop(0)
        self._time += 1
        a = AckRecord(self._next(), self._time, station_id, send_id, price)
        self.acknowledgements.append(a)
        self.app.on_acknowledgement(station_id, send_id, price)
        return a

    def _run_due_submits(self, force=False):
        ran = False
        while self._schedule and (force or self._schedule[0][0] <= self._steps):
            _, _, st, pr = self._schedule.pop(0)
            self.submit(st, pr)
            ran = True
            force = False
        return ran

    def step(self):
        """One transport step. Returns False when nothing is in flight."""
        self._run_due_submits()
        if self._ack_queue:
            self.deliver_ack()
        else:
            rec = self._pick()
            if rec is None:
                if self._run_due_submits(force=True):
                    self._steps += 1
                    return True
                return False
            self._deliver(rec)
        self._steps += 1
        return True

    def run_until_idle(self, max_steps=100000):
        n = 0
        while self.step():
            n += 1
            if n >= max_steps:
                raise RuntimeError("simulation did not become idle")
        return n

    # ---- observation --------------------------------------------------
    def station_price(self, station_id):
        return self.station_prices.get(station_id)

    def events(self):
        allrec = self.sends + self.deliveries + self.acknowledgements + self.submissions
        return sorted(allrec, key=lambda r: r.event_index)
