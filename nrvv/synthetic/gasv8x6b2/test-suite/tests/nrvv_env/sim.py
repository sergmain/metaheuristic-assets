import random


class SubmissionRejected(Exception):
    pass


class Simulation:
    """Simulated stations, transport, pricing team and clock for the price service."""

    def __init__(self, seed=0, cost_per_send=1.0, stale_cost_per_time=1.0,
                 loss_probability=0.0, start_time=0.0, ordering="random"):
        self.seed = seed
        self.rng = random.Random(seed)
        self.cost_per_send = cost_per_send
        self.stale_cost_per_time = stale_cost_per_time
        self.loss_probability = loss_probability
        self.ordering = ordering  # "random" or "fifo"
        self._time = start_time
        self._event = 0
        self.app = None
        self.station_prices = {}      # station_id -> current price (None if never set)
        self.station_applied = {}     # station_id -> list of (event_index, request_id, price)
        self.sends = []               # recorded sends
        self.deliveries = []          # recorded deliveries to stations
        self.acknowledgements = []    # recorded acks delivered to the service
        self.losses = []
        self.submissions = []
        self.rejections = []
        self._state = {}              # seq -> inflight|delivered|acked|lost
        self._arrival_script = []     # list of send ordinals in scripted arrival order
        self._lose_ordinals = set()
        self._scheduled = []          # (time, order, station_id, price)
        self._sched_counter = 0

    # ---- clock ----
    def now(self):
        return self._time

    def set_time(self, t):
        self._time = t

    def advance(self, dt):
        self._time += dt

    def advance_to(self, t):
        """Advance the clock to t, performing scheduled submissions that fall due."""
        while True:
            due = [s for s in self._scheduled if s[0] <= t]
            if not due:
                break
            due.sort(key=lambda s: (s[0], s[1]))
            s = due[0]
            self._scheduled.remove(s)
            if s[0] > self._time:
                self._time = s[0]
            self.submit(s[2], s[3])
        if t > self._time:
            self._time = t

    # ---- scripting ----
    def set_arrival_order(self, ordinals):
        """Scripted arrival order of sends, by 0-based send ordinal (order of request)."""
        self._arrival_script = list(ordinals)

    def lose_send(self, ordinal):
        self._lose_ordinals.add(ordinal)

    def schedule_submit(self, at, station_id, price):
        self._sched_counter += 1
        self._scheduled.append((at, self._sched_counter, station_id, price))

    # ---- events ----
    def _next_event(self):
        self._event += 1
        return self._event

    # ---- wiring ----
    def connect(self, app):
        """Connect the app (module or object) through closure ports."""
        self.app = app
        sim = self

        def send_to_station(station_id, price, version, request_id):
            seq = len(sim.sends)
            sim.sends.append({
                "event_index": sim._next_event(), "ordinal": seq, "time": sim._time,
                "station_id": station_id, "price": price, "version": version,
                "request_id": request_id,
            })
            sim._state[seq] = "inflight"
            if sim.station_prices.get(station_id) is None:
                sim.station_prices.setdefault(station_id, None)
            return None

        def now():
            return sim._time

        def get_cost_rates():
            return {"cost_per_send": sim.cost_per_send,
                    "cost_per_stale_time": sim.stale_cost_per_time,
                    "cost_per_unit_time_stale": sim.stale_cost_per_time}

        ports = {
            "send_to_station": send_to_station,
            "now": now,
            "get_time": now,
            "get_cost_rates": get_cost_rates,
            "get_rates": get_cost_rates,
        }
        hook = getattr(app, "connect", None)
        if callable(hook):
            try:
                hook(**ports)
            except TypeError:
                hook(ports)
        return ports

    # ---- pricing team ----
    def submit(self, station_id, price):
        ev = self._next_event()
        try:
            uid = self.app.submit_price_update(station_id, price, self._time)
        except Exception as exc:  # rejection by the service
            self.rejections.append({"event_index": ev, "time": self._time,
                                    "station_id": station_id, "price": price,
                                    "error": exc})
            raise
        self.submissions.append({"event_index": ev, "time": self._time,
                                 "station_id": station_id, "price": price,
                                 "update_id": uid})
        return uid

    # ---- transport ----
    def _inflight(self):
        return [i for i, s in self._state.items() if s == "inflight"]

    def _ack_candidate(self):
        open_ = [i for i, s in self._state.items() if s in ("inflight", "delivered")]
        if not open_:
            return None
        low = min(open_)
        return low if self._state[low] == "delivered" else None

    def pending(self):
        return len(self._inflight()) + sum(
            1 for s in self._state.values() if s == "delivered")

    def idle(self):
        return self.pending() == 0

    def _pick_send(self):
        inflight = self._inflight()
        for o in self._arrival_script:
            if o in inflight:
                return o
        if self.ordering == "fifo":
            return min(inflight)
        return self.rng.choice(sorted(inflight))

    def step_send(self):
        if not self._inflight():
            return False
        seq = self._pick_send()
        send = self.sends[seq]
        lose = seq in self._lose_ordinals or (
            self.loss_probability > 0 and self.rng.random() < self.loss_probability)
        if lose:
            self._state[seq] = "lost"
            self.losses.append({"event_index": self._next_event(), "time": self._time,
                                "ordinal": seq, "station_id": send["station_id"],
                                "request_id": send["request_id"]})
            return True
        sid = send["station_id"]
        ev = self._next_event()
        self.station_prices[sid] = send["price"]
        self.station_applied.setdefault(sid, []).append((ev, send["request_id"], send["price"]))
        self.deliveries.append({"event_index": ev, "time": self._time, "ordinal": seq,
                                "station_id": sid, "price": send["price"],
                                "request_id": send["request_id"]})
        self._state[seq] = "delivered"
        return True

    def step_ack(self):
        seq = self._ack_candidate()
        if seq is None:
            return False
        send = self.sends[seq]
        self._state[seq] = "acked"
        rec = {"event_index": self._next_event(), "time": self._time, "ordinal": seq,
               "station_id": send["station_id"], "request_id": send["request_id"],
               "outcome": "ok"}
        self.acknowledgements.append(rec)
        self.app.on_acknowledgement(send["station_id"], send["request_id"], "ok")
        return True

    def step(self):
        """One transport step: deliver a send to a station or an ack to the service."""
        can_send = bool(self._inflight())
        can_ack = self._ack_candidate() is not None
        if not can_send and not can_ack:
            return False
        if can_send and can_ack:
            if self.rng.random() < 0.5:
                return self.step_ack()
            return self.step_send()
        return self.step_ack() if can_ack else self.step_send()

    def run_until_idle(self, max_steps=100000):
        n = 0
        while self.step():
            n += 1
            if n >= max_steps:
                raise RuntimeError("simulation did not become idle")
        return n

    # ---- observation ----
    def station_price(self, station_id):
        return self.station_prices.get(station_id)

    def traffic(self):
        return {"sends": list(self.sends), "deliveries": list(self.deliveries),
                "acknowledgements": list(self.acknowledgements),
                "losses": list(self.losses)}
