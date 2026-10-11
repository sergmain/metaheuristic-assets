"""Simulated environment for the server side: price source, stations and transport.

The test hands in a server factory, server_factory(dispatch_update), which returns the server side
object. That object must provide set_desired_price(station_id, price), acknowledgement_received(
station_id, sequence, price), reachability_changed(station_id, reachable) and station_state(station_id).
The simulation calls dispatch_update(station_id, sequence, price) for every server send.
Nothing here imports the server side, reads a clock, or does real I/O.
"""

import heapq
import random
from collections import namedtuple
from itertools import chain
from operator import attrgetter

PRICES = (1.25, 1.35, 1.45, 1.55, 1.65)
CALL_GAP = (0.2, 2.0)
BURST_PROBABILITY = 0.4
BURST_SIZE = (2, 4)
BURST_GAP = (0.05, 0.5)
UPDATE_DELAY = (0.0, 2.0)
ACK_DELAY = (0.0, 1.0)
REACHABLE_SPAN = (3.0, 15.0)
UNREACHABLE_SPAN = (1.0, 6.0)
HORIZON_MARGIN = 200.0

# At equal logical time, reachability notices are delivered before everything else.
REACH_PRIORITY = 0
OTHER_PRIORITY = 1

Desired = namedtuple("Desired", "order time station price")
Dispatch = namedtuple("Dispatch", "order time station sequence price reachable")
Delivery = namedtuple("Delivery", "order time station sequence price")
Ack = namedtuple("Ack", "order time station sequence price")
DisplayChange = namedtuple("DisplayChange", "order time station price")
ReachabilityChange = namedtuple("ReachabilityChange", "order time station reachable")


class Station:
    """Fixed station model: shows the last received price and acknowledges each receipt."""

    def __init__(self, station_id):
        self.station_id = station_id
        self.display = None

    def receive(self, sequence, price):
        self.display = price
        return sequence, price


class Simulation:
    """Clients and transport driven by a logical clock that only the test steps.

    Randomness comes only from random.Random(seed). Records of every call, dispatch, delivery,
    acknowledgement, display change and reachability change are kept for the oracle checks.
    Stations start reachable at time 0 and no notice is sent for that initial state.
    """

    def __init__(self, seed, server_factory, *, stations=4, stop_time=30.0, forced_reachable=None):
        self._rng = random.Random(seed)
        self.now = 0.0
        self.station_ids = tuple(f"st{i}" for i in range(1, stations + 1))
        self._heap = []
        self._counter = 0
        self._order = 0
        self._inflight = 0
        self._last_call_time = None
        self._models = {s: Station(s) for s in self.station_ids}
        self._reachable = {s: True for s in self.station_ids}
        self._held = {s: [] for s in self.station_ids}
        self._last_ack_time = {s: 0.0 for s in self.station_ids}
        self.desired = []
        self.dispatches = []
        self.deliveries = []
        self.acks = []
        self.display_changes = []
        self.reachability_changes = []
        self.call_results = []
        self._schedule_price_source(stop_time)
        self._schedule_reachability(stop_time, forced_reachable or {})
        self.server = server_factory(self.dispatch_update)

    # ----- scheduling -------------------------------------------------------

    def _push(self, time, priority, kind, payload):
        heapq.heappush(self._heap, (time, priority, self._counter, kind, payload))
        self._counter += 1

    def _push_call(self, time, station, price):
        self._push(time, OTHER_PRIORITY, "call", (station, price))
        self._inflight += 1
        self._last_call_time = time

    def _schedule_price_source(self, stop_time):
        rng, t = self._rng, 0.0
        while True:
            t += rng.uniform(*CALL_GAP)
            if t > stop_time:
                break
            station = rng.choice(self.station_ids)
            self._push_call(t, station, rng.choice(PRICES))
            if rng.random() < BURST_PROBABILITY:
                for _ in range(rng.randint(*BURST_SIZE) - 1):
                    t += rng.uniform(*BURST_GAP)
                    if t > stop_time:
                        break
                    self._push_call(t, station, rng.choice(PRICES))

    def _schedule_reachability(self, stop_time, forced):
        rng, horizon = self._rng, stop_time + HORIZON_MARGIN
        for s in self.station_ids:
            transitions, t, state = [], 0.0, True
            while True:
                t += rng.uniform(*(REACHABLE_SPAN if state else UNREACHABLE_SPAN))
                if t > horizon:
                    break
                state = not state
                transitions.append((t, state))
            if s in forced:
                f = forced[s]
                before = [(time, st) for time, st in transitions if time < f]
                state_at_f = before[-1][1] if before else True
                transitions = before + ([] if state_at_f else [(f, True)])
            for time, st in transitions:
                self._push(time, REACH_PRIORITY, "reach", (s, st))

    # ----- the server-facing outbound port ----------------------------------

    def dispatch_update(self, station_id, sequence, price):
        self.dispatches.append(Dispatch(self._next_order(), self.now, station_id, sequence, price,
                                        self._reachable[station_id]))
        self._push(self.now + self._rng.uniform(*UPDATE_DELAY), OTHER_PRIORITY, "deliver",
                   (station_id, sequence, price))
        self._inflight += 1

    # ----- driver -----------------------------------------------------------

    def step(self):
        """Process the next event, advancing the clock to its time. Returns False if none is left."""
        if not self._heap:
            return False
        time, _, _, kind, payload = heapq.heappop(self._heap)
        self.now = time
        if kind == "call":
            self._on_call(*payload)
        elif kind == "reach":
            self._on_reach(*payload)
        elif kind == "deliver":
            self._on_deliver(*payload)
        else:
            self._on_ack(*payload)
        return True

    def run_until(self, time):
        """Process every event due up to and including time, then advance the clock to time."""
        while self._heap and self._heap[0][0] <= time:
            self.step()
        self.now = max(self.now, time)
        return self.now

    def run_until_quiet(self, limit=None):
        """Step until no call, delivery or acknowledgement is in flight (or the limit is passed)."""
        while self._inflight > 0 and self._heap:
            if limit is not None and self._heap[0][0] > limit:
                break
            self.step()
        return self.now

    def in_flight(self):
        return self._inflight

    @property
    def last_desired_time(self):
        return self._last_call_time

    def reachable(self, station_id):
        return self._reachable[station_id]

    def display(self, station_id):
        return self._models[station_id].display

    def state(self, station_id):
        """Forwards to the server side's station_state (observation only)."""
        return self.server.station_state(station_id)

    # ----- event handlers ---------------------------------------------------

    def _next_order(self):
        self._order += 1
        return self._order

    def _on_call(self, station, price):
        self._inflight -= 1
        self.desired.append(Desired(self._next_order(), self.now, station, price))
        self.call_results.append(self.server.set_desired_price(station, price))

    def _on_reach(self, station, state):
        self._reachable[station] = state
        self.reachability_changes.append(ReachabilityChange(self._next_order(), self.now, station, state))
        self.server.reachability_changed(station, state)
        if state:
            for seq, price in self._held[station]:
                self._push(self.now + self._rng.uniform(*UPDATE_DELAY), OTHER_PRIORITY, "deliver",
                           (station, seq, price))
            self._held[station] = []

    def _on_deliver(self, station, sequence, price):
        if not self._reachable[station]:
            self._held[station].append((sequence, price))
            return
        self._inflight -= 1
        self.deliveries.append(Delivery(self._next_order(), self.now, station, sequence, price))
        model = self._models[station]
        before = model.display
        echo_seq, echo_price = model.receive(sequence, price)
        if model.display != before:
            self.display_changes.append(DisplayChange(self._next_order(), self.now, station, price))
        t = max(self.now + self._rng.uniform(*ACK_DELAY), self._last_ack_time[station])
        self._last_ack_time[station] = t
        self._push(t, OTHER_PRIORITY, "ack", (station, echo_seq, echo_price))
        self._inflight += 1

    def _on_ack(self, station, sequence, price):
        self._inflight -= 1
        self.acks.append(Ack(self._next_order(), self.now, station, sequence, price))
        self.server.acknowledgement_received(station, sequence, price)

    # ----- oracle -----------------------------------------------------------

    def _timeline(self):
        return sorted(chain(self.desired, self.dispatches, self.acks, self.reachability_changes,
                            self.display_changes), key=attrgetter("order"))

    def check_r6(self):
        """Every dispatch carries the latest desired price for its station at its time."""
        latest, problems = {}, []
        for r in self._timeline():
            if isinstance(r, Desired):
                latest[r.station] = r.price
            elif isinstance(r, Dispatch) and latest.get(r.station) != r.price:
                problems.append(f"R6 dispatch not latest: {r}")
        return problems

    def check_repeats(self):
        """A dispatch repeating the last sent price must follow an ack carrying a non-latest price."""
        latest, last_sent, stale, problems = {}, {}, {}, []
        for r in self._timeline():
            if isinstance(r, Desired):
                latest[r.station] = r.price
            elif isinstance(r, Ack):
                if latest.get(r.station) != r.price:
                    stale[r.station] = True
            elif isinstance(r, Dispatch):
                s = r.station
                if s in last_sent and last_sent[s] == r.price and not stale.get(s):
                    problems.append(f"R4/R5 repeated price without stale ack: {r}")
                last_sent[s] = r.price
                stale[s] = False
        return problems

    def check_reachable_dispatch(self):
        """No dispatch is sent to an unreachable station."""
        return [f"R7 dispatch to unreachable station: {r}" for r in self.dispatches if not r.reachable]

    def _reachable_throughout(self, station, start, end):
        state = True
        for r in self.reachability_changes:
            if r.station != station:
                continue
            if r.time <= start:
                state = r.reachable
            elif r.time <= end:
                return False
        return state

    def _display_at(self, station, time):
        shown = None
        for r in self.display_changes:
            if r.station == station and r.time <= time:
                shown = r.price
        return shown

    def check_convergence(self, bound=10.0):
        """Stations reachable throughout [last desired change, last change + bound] show the latest price.

        Requires the clock to have reached last change + bound. Stations never called are skipped.
        """
        if self._last_call_time is None:
            return []
        end = self._last_call_time + bound
        if self.now < end:
            raise ValueError(f"run the simulation to {end} before checking convergence")
        latest = {}
        for r in self.desired:
            latest[r.station] = r.price
        problems = []
        for station, price in latest.items():
            if not self._reachable_throughout(station, self._last_call_time, end):
                continue
            shown = self._display_at(station, end)
            if shown != price:
                problems.append(f"R7 {station} shows {shown}, latest {price} at {end}")
        return problems

    def check_all(self, bound=10.0):
        return {
            "R6": self.check_r6(),
            "R4_R5": self.check_repeats(),
            "R7_dispatch": self.check_reachable_dispatch(),
            "R7_convergence": self.check_convergence(bound),
            "D8_convergence": self.check_convergence(6.0),
        }
