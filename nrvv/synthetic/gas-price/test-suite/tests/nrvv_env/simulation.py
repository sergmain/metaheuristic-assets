"""The simulated Environment around the price-update service.

What is simulated (and nothing more):

* TMPGASDF1-15  A price-source client that issues a deterministic, seeded script of
  ``set-desired-price`` calls, including bursts that set several desired prices for
  one station in quick succession. It is the only producer of desired prices.
* TMPGASDF1-16  A reliable, clock-free, discrete-event transport. Update deliveries
  toward stations may be reordered relative to one another (seeded scheduler);
  acknowledgements back to the service are delivered per station in the order the
  corresponding updates were received. Nothing is lost or duplicated.
* TMPGASDF1-17  Stations that display the last update they received and acknowledge
  each received update (echoing its identifier) in receipt order, and are otherwise
  immutable and never originate a price.
* TMPGASDF1-18  Full observability of every send, delivery and acknowledgement, and
  each station's current displayed price.

The server side (``app``) is NOT implemented here. The simulation only invokes the
server's inbound operations (``set_desired_price``, ``receive_acknowledgement``) and
receives the server's outbound ``send_update`` calls through the port handed to it.

Everything is deterministic: no threads, no clock, no real I/O. All non-determinism
flows from a single ``random.Random(seed)`` built from the seed the test supplies.
"""
import random
from collections import deque, namedtuple

__all__ = [
    "Simulation",
    "Station",
    "SendRecord",
    "DeliveryRecord",
    "AckRecord",
    "InputRecord",
]

# Records logged on the observable boundary (TMPGASDF1-18).
SendRecord = namedtuple("SendRecord", "station update_id price")
DeliveryRecord = namedtuple("DeliveryRecord", "station update_id price")
AckRecord = namedtuple("AckRecord", "station update_id price")
InputRecord = namedtuple("InputRecord", "station price")


class Station:
    """A simulated station (TMPGASDF1-17).

    Holds a single displayed price equal to the last update received, and keeps a
    FIFO queue of acknowledgements to emit in receipt order. It is never altered by
    any other means and never originates a price.
    """

    def __init__(self, ident):
        self.ident = ident
        self.displayed = None          # last received update's price
        self.received = []             # history of received prices, in receipt order
        self.ack_queue = deque()       # pending (update_id, price), receipt order

    def receive(self, update_id, price):
        self.displayed = price
        self.received.append(price)
        self.ack_queue.append((update_id, price))

    def __repr__(self):
        return "Station(%r, displayed=%r)" % (self.ident, self.displayed)


class Simulation:
    """A seeded, deterministic run of the Environment around one server instance.

    Build from a seed, connect the server, then drive it step by step (``step``) or
    to quiescence (``run``). Observe via the logs and the station views.
    """

    def __init__(self, seed, server=None, *, num_stations=4, num_bursts=10,
                 max_burst=3, price_range=(1, 20)):
        self.seed = seed
        self._random = random.Random(seed)
        self.num_stations = num_stations
        self.station_ids = ["S%d" % i for i in range(num_stations)]
        self.stations = {sid: Station(sid) for sid in self.station_ids}

        # transport state
        self._pending_updates = []     # SendRecords sent but not yet delivered
        self._active_burst = deque()   # remaining inputs of the burst in progress

        # observable logs (TMPGASDF1-18)
        self.send_log = []
        self.delivery_log = []
        self.ack_log = []
        self.input_log = []

        # server wiring
        self.server = None
        self._set_desired = None
        self._receive_ack = None

        # seeded price-source script (TMPGASDF1-15)
        self._bursts = self._generate_script(num_bursts, max_burst, price_range)

        if server is not None:
            self.connect(server)

    # -- wiring ----------------------------------------------------------------
    def connect(self, server):
        """Register the server instance (``app``) exposing the inbound operations.

        ``server`` must provide callables ``set_desired_price(station, price)`` and
        ``receive_acknowledgement(station, update_id)``. The outbound port the
        server calls is :meth:`send_update` (available before ``connect`` so it can
        be handed to ``app`` at construction time).
        """
        set_desired = getattr(server, "set_desired_price", None)
        receive_ack = getattr(server, "receive_acknowledgement", None)
        if not callable(set_desired) or not callable(receive_ack):
            raise TypeError(
                "server must provide callable set_desired_price(station, price) "
                "and receive_acknowledgement(station, update_id)")
        self.server = server
        self._set_desired = set_desired
        self._receive_ack = receive_ack
        return self

    # -- outbound port handed to `app` (TMPGASDF1-12) --------------------------
    def send_update(self, station, update_id, price):
        """The send-update port: the service hands one update to the transport.

        We record it and hold it for later (possibly reordered) delivery. The
        service assigns ``update_id``; we only carry it through.
        """
        rec = SendRecord(station, update_id, price)
        self.send_log.append(rec)
        self._pending_updates.append(rec)

    # -- seeded script ---------------------------------------------------------
    def _generate_script(self, num_bursts, max_burst, price_range):
        lo, hi = price_range
        cap = max(1, max_burst)
        bursts = deque()
        for _ in range(max(0, num_bursts)):
            station = self._random.choice(self.station_ids)
            n = self._random.randint(1, cap)
            burst = [(station, self._random.randint(lo, hi)) for _ in range(n)]
            bursts.append(burst)
        return bursts

    # -- event execution -------------------------------------------------------
    def _require_server(self):
        if self._set_desired is None or self._receive_ack is None:
            raise RuntimeError("no server connected; call connect(server) first")

    def _deliver_input(self):
        self._require_server()
        station, price = self._active_burst.popleft()
        rec = InputRecord(station, price)
        self.input_log.append(rec)
        # drives R1's send trigger; the server may call send_update synchronously
        self._set_desired(station, price)
        return rec

    def _deliver_update(self, upd):
        for i, x in enumerate(self._pending_updates):
            if x is upd:
                del self._pending_updates[i]
                break
        st = self.stations[upd.station]
        st.receive(upd.update_id, upd.price)
        rec = DeliveryRecord(upd.station, upd.update_id, upd.price)
        self.delivery_log.append(rec)
        return rec

    def _deliver_ack(self, sid):
        self._require_server()
        st = self.stations[sid]
        update_id, price = st.ack_queue.popleft()
        rec = AckRecord(sid, update_id, price)
        self.ack_log.append(rec)
        # the server clears the slot, records displayed, re-evaluates (may send)
        self._receive_ack(sid, update_id)
        return rec

    # -- driving ---------------------------------------------------------------
    def step(self):
        """Execute one scheduled event; return its record, or ``None`` if quiescent.

        An input burst is delivered in quick succession: while a burst is in
        progress its remaining inputs are delivered before any transport event, so
        several desired prices land on one station without an intervening
        acknowledgement (exercising coalescing). Otherwise the seeded scheduler
        chooses uniformly among starting the next burst, delivering any pending
        update (updates may be reordered), and delivering the head acknowledgement
        of any station (acks stay in per-station receipt order).
        """
        if self._active_burst:
            return self._deliver_input()

        actions = []
        if self._bursts:
            actions.append(("burst", None))
        for upd in self._pending_updates:
            actions.append(("update", upd))
        for sid in self.station_ids:
            if self.stations[sid].ack_queue:
                actions.append(("ack", sid))

        if not actions:
            return None

        kind, arg = actions[self._random.randrange(len(actions))]
        if kind == "burst":
            self._active_burst = deque(self._bursts.popleft())
            return self._deliver_input()
        if kind == "update":
            return self._deliver_update(arg)
        return self._deliver_ack(arg)

    def run(self, max_steps=1000000):
        """Drive until nothing is in flight; return the number of steps executed."""
        steps = 0
        while True:
            ev = self.step()
            if ev is None:
                return steps
            steps += 1
            if steps > max_steps:
                raise RuntimeError(
                    "simulation did not reach quiescence within %d steps" % max_steps)

    run_until_quiescent = run

    def is_quiescent(self):
        """True when the script is exhausted and nothing is in flight."""
        if self._active_burst or self._bursts or self._pending_updates:
            return False
        return not any(self.stations[s].ack_queue for s in self.station_ids)

    # -- observation helpers ---------------------------------------------------
    def displayed(self, station):
        """The station's current displayed price (``None`` if nothing received)."""
        return self.stations[station].displayed

    def pending_updates(self):
        """Updates sent but not yet delivered (copy of the in-flight list)."""
        return list(self._pending_updates)

    def in_flight(self):
        """Total number of things not yet settled: queued inputs, undelivered
        updates and undelivered acknowledgements."""
        acks = sum(len(self.stations[s].ack_queue) for s in self.station_ids)
        remaining_script = sum(len(b) for b in self._bursts)
        return (len(self._active_burst) + remaining_script
                + len(self._pending_updates) + acks)

    # -- optional manual injection --------------------------------------------
    def inject_desired(self, station, price):
        """Manually issue one set-desired-price call (forwards to the server).

        A convenience for tests that want to drive a specific desired price rather
        than rely on the seeded script; it adds no behaviour of its own.
        """
        self._require_server()
        rec = InputRecord(station, price)
        self.input_log.append(rec)
        self._set_desired(station, price)
        return rec
