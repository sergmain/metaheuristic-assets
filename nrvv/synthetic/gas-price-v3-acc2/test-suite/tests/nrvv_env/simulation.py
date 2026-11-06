"""Deterministic simulation of the environment around the server side `app`.

No threads, no clock, no real I/O. All randomness flows through a single
``random.Random(seed)`` instance, so the same seed always produces the same run.

Wiring (done by the test, which knows both `app` and this package):

    import app, nrvv_env

    sim = nrvv_env.Simulation.from_seed(1234)
    # The simulation exposes the outbound transmit port as a plain callable.
    server = app.Server(sim.transmit)        # however `app` wants it wired
    sim.bind(server)                         # or: server = sim.connect(factory)
    sim.run()                                # drive until quiescent

    # observe
    sim.sent            # ordered log of emitted updates   (station, price)
    sim.delivered       # ordered log of deliveries        (station, price)
    sim.acknowledged    # ordered log of acknowledgements   (station, price)
    sim.applied(s)      # a modeled station's current applied price
    server.get_station_state(s)              # the server's reconciliation state
"""

import random


class Update(object):
    """One price update emitted by the server through the transmit port.

    Lifecycle: EMITTED -> DELIVERED -> ACKED.
    """

    EMITTED = "emitted"
    DELIVERED = "delivered"
    ACKED = "acked"

    __slots__ = ("seq", "station", "price", "state")

    def __init__(self, seq, station, price):
        self.seq = seq
        self.station = station
        self.price = price
        self.state = Update.EMITTED

    def __repr__(self):
        return "Update(seq=%r, station=%r, price=%r, state=%r)" % (
            self.seq, self.station, self.price, self.state,
        )


class Station(object):
    """A dumb, version-free station (GASV3ACC2-24).

    It holds a single applied-price slot which it overwrites with whatever
    update it receives. It performs no comparison or de-duplication, retains no
    history of values, emits exactly one acknowledgement per received update,
    and never rejects an update.
    """

    __slots__ = ("ident", "applied", "received_count")

    def __init__(self, ident):
        self.ident = ident
        self.applied = None          # no update received yet
        self.received_count = 0

    def apply(self, price):
        """Adopt the carried price as the applied value (GASV3ACC2-21/-24)."""
        self.applied = price
        self.received_count += 1

    def __repr__(self):
        return "Station(ident=%r, applied=%r, received_count=%r)" % (
            self.ident, self.applied, self.received_count,
        )


class Simulation(object):
    """The simulated environment: producers + transport + stations.

    Construct with an explicit event sequence, or via :meth:`from_seed` to let a
    seeded producer generate one. Either way all nondeterminism (producer
    sequence *and* transport delivery order) is driven by one seeded RNG.
    """

    def __init__(self, events, seed=0, rng=None):
        self._rng = rng if rng is not None else random.Random(seed)
        self._events = [(s, p) for (s, p) in events]   # producer sequence
        self._event_index = 0
        self._server = None

        self._updates = []        # every update ever emitted, in emit order
        self._inflight = []       # updates not yet acknowledged, in emit order
        self._stations = {}       # ident -> Station
        self._emit_seq = 0

        # observation logs (GASV3ACC2-23)
        self.sent = []            # (station, price), emit order
        self.delivered = []       # (station, price), delivery order
        self.acknowledged = []    # (station, price), acknowledgement order

        # Pre-create station models for everything the producers will mention,
        # so tests can observe them even before any delivery.
        for s, _ in self._events:
            self._station(s)

    # ----- construction helpers -------------------------------------------

    @classmethod
    def from_seed(cls, seed, num_stations=3, num_events=20,
                  price_min=1, price_max=100, station_names=None):
        """Build a simulation whose producer sequence is generated from `seed`
        (GASV3ACC2-20). The same RNG instance then drives transport ordering,
        so the whole run is reproducible from the one seed.
        """
        rng = random.Random(seed)
        if station_names is None:
            station_names = ["S%d" % i for i in range(num_stations)]
        station_names = list(station_names)
        events = []
        for _ in range(num_events):
            s = rng.choice(station_names)
            p = rng.randint(price_min, price_max)
            events.append((s, p))
        return cls(events, rng=rng)

    # ----- wiring ----------------------------------------------------------

    def bind(self, server):
        """Attach a server whose outbound transmit port is already wired to
        :meth:`transmit`. The simulation drives it via its inbound operations.
        """
        self._server = server
        return self

    def connect(self, factory):
        """Convenience: build the server with ``factory(self.transmit)`` and
        bind it. Returns the created server.
        """
        server = factory(self.transmit)
        self._server = server
        return server

    # ----- outbound port (GASV3ACC2-16) -----------------------------------

    def transmit(self, station, price):
        """The outbound transmit port the server invokes to emit a price update.

        Carries only (station, price) -- no sequence number or version. The act
        of invoking it hands the update to the transport (GASV3ACC2-16). May be
        called re-entrantly while a submit/ack is being processed.
        """
        self._station(station)
        u = Update(self._emit_seq, station, price)
        self._emit_seq += 1
        self._updates.append(u)
        self._inflight.append(u)
        self.sent.append((station, price))
        return u

    # ----- driving ---------------------------------------------------------

    def step(self):
        """Perform one atomic environment action and return a description of it,
        or ``None`` when nothing remains to do.

        An action is one of:
          ('submit', station, price)   -- fire the next producer event
          ('deliver', update)          -- deliver an in-flight update
          ('ack', update)              -- return an acknowledgement

        The choice among currently-available actions is made with the seeded
        RNG, which is how out-of-order delivery (GASV3ACC2-21) is realized.
        """
        actions = self._available_actions()
        if not actions:
            return None
        action = self._rng.choice(actions)
        return self._perform(action)

    def run(self, max_steps=None):
        """Drive the server through the transport until nothing is in flight
        (every producer event submitted, every emitted update delivered and
        acknowledged, GASV3ACC2-21 eventual delivery). Returns the step count.
        """
        count = 0
        while True:
            if max_steps is not None and count >= max_steps:
                break
            if self.step() is None:
                break
            count += 1
        return count

    # ----- action machinery ------------------------------------------------

    def _available_actions(self):
        acts = []
        if self._event_index < len(self._events):
            s, p = self._events[self._event_index]
            acts.append(("submit", s, p))

        # First still-unacknowledged update per station, in emit order. Only
        # that one may be acknowledged next, enforcing per-station in-order
        # acknowledgement (GASV3ACC2-22).
        earliest = {}
        for u in self._inflight:
            if u.station not in earliest:
                earliest[u.station] = u

        for u in self._inflight:
            if u.state == Update.EMITTED:
                acts.append(("deliver", u))
            elif u.state == Update.DELIVERED and earliest.get(u.station) is u:
                acts.append(("ack", u))
        return acts

    def _perform(self, action):
        kind = action[0]
        if kind == "submit":
            s, p = action[1], action[2]
            self._event_index += 1
            # May re-enter transmit() if the server decides to emit.
            self._server.submit_desired_price(s, p)
            return action
        if kind == "deliver":
            u = action[1]
            u.state = Update.DELIVERED
            self._station(u.station).apply(u.price)
            self.delivered.append((u.station, u.price))
            return action
        if kind == "ack":
            u = action[1]
            u.state = Update.ACKED
            self._inflight.remove(u)
            self.acknowledged.append((u.station, u.price))
            # Injected after the station applied the update (GASV3ACC2-22).
            # May re-enter transmit() if the server emits the next update.
            self._server.acknowledgement_received(u.station)
            return action
        raise ValueError("unknown action: %r" % (action,))

    # ----- observation surface (GASV3ACC2-23) -----------------------------

    def _station(self, ident):
        st = self._stations.get(ident)
        if st is None:
            st = Station(ident)
            self._stations[ident] = st
        return st

    def station(self, ident):
        """The modeled :class:`Station` for `ident` (created on demand)."""
        return self._station(ident)

    def applied(self, ident):
        """The station's current applied price (``None`` if nothing delivered)."""
        return self._station(ident).applied

    @property
    def stations(self):
        """A snapshot mapping of station ident -> :class:`Station`."""
        return dict(self._stations)

    @property
    def emitted(self):
        """Alias for :attr:`sent`: the ordered emit log (station, price)."""
        return list(self.sent)

    @property
    def in_flight(self):
        """The updates emitted but not yet acknowledged, in emit order."""
        return list(self._inflight)

    @property
    def pending_events(self):
        """Producer events not yet submitted, in order."""
        return self._events[self._event_index:]

    def quiescent(self):
        """True once every producer event is submitted and nothing is in flight."""
        return self._event_index >= len(self._events) and not self._inflight

    def get_station_state(self, ident):
        """Pass-through to the server's observation operation (GASV3ACC2-19)."""
        return self._server.get_station_state(ident)


def build(seed, **kwargs):
    """Shorthand for :meth:`Simulation.from_seed`."""
    return Simulation.from_seed(seed, **kwargs)
