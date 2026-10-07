"""Deterministic, clock-free simulation of the GASV3DEV3 environment.

No threads, no wall clock, no real I/O.  All non-determinism is funnelled
through a single ``random.Random(seed)`` instance so the same seed (and the
same script and the same server) reproduce the same run exactly.
"""

import random

# Sentinel meaning a station's displayed value is not (yet) known.
UNKNOWN = None


class Update:
    """One update in flight on the station-bound channel (one send-update)."""

    __slots__ = ("seq", "station", "price")

    def __init__(self, seq, station, price):
        self.seq = seq
        self.station = station
        self.price = price

    def __iter__(self):
        # Allows:  station, price = update
        return iter((self.station, self.price))

    def __repr__(self):
        return "Update(seq=%r, station=%r, price=%r)" % (
            self.seq, self.station, self.price)


class Ack:
    """One acknowledgement travelling back to the server (in emission order)."""

    __slots__ = ("seq", "station", "update_seq")

    def __init__(self, seq, station, update_seq):
        self.seq = seq
        self.station = station
        self.update_seq = update_seq

    def __repr__(self):
        return "Ack(seq=%r, station=%r, update_seq=%r)" % (
            self.seq, self.station, self.update_seq)


class Simulation:
    """Wires the simulated environment to a server-side ``app`` object.

    The server object passed in must expose the inbound Interface operations
    ``submit_desired_price(station, price)``, ``acknowledge(station)`` and
    ``inspect_station(station)``.  The outbound ``send-update`` port is
    supplied by this object as ``self.outbound`` (also aliased
    ``self.send_update``); a test wires it into the server either by
    constructor injection or by letting ``attach(..., wire_outbound=True)``
    set the named attribute on the server.

    Driving the run:
      * ``step()``  advances exactly one logical event chosen by the seeded
        scheduler among the ready actions, or returns ``None`` when quiescent.
      * ``run()``   repeats ``step()`` until nothing is pending or in flight.
      * Explicit drivers ``fire_submission()``, ``deliver(seq)`` and
        ``deliver_ack()`` give fine-grained, deterministic control.

    Observation:
      * ``sent``      - list of (station, price) for every send-update, in order
      * ``delivered`` - list of (station, price) for every delivery, in order
      * ``acks``      - list of station ids for every ack delivered to server
      * ``history``   - full ordered trace of ('submit'|'deliver'|'ack', ...)
      * ``displayed(station)`` - the value a station currently shows (or UNKNOWN)
      * ``inspect(station)``   - delegates to the server's inspect-station query
    """

    def __init__(self, server=None, seed=0, script=None,
                 wire_outbound=False, port_attr="send_update"):
        self.seed = seed
        self.random = random.Random(seed)

        # Scripted client submissions, consumed in fixed script order.
        self._submissions = list(script) if script is not None else []
        self._sub_index = 0

        # Station-bound channel: reliable, exactly-once, reorderable.
        self.station_channel = []          # list[Update]
        # Acknowledgement channel: order-preserving FIFO back to the server.
        self.ack_channel = []              # list[Ack]

        # Each passive station displays the last value it received.
        self.displays = {}                 # station -> price

        # Observations.
        self.sent = []                     # list[(station, price)]
        self.delivered = []                # list[(station, price)]
        self.acks = []                     # list[station]
        self.history = []                  # list[tuple]

        self._update_seq = 0
        self._ack_seq = 0

        self.server = None
        # The outbound send-update port.  Available before attach() so a test
        # can inject it when constructing the server.
        self.outbound = self._outbound
        self.send_update = self._outbound

        if server is not None:
            self.attach(server, wire_outbound=wire_outbound,
                        port_attr=port_attr)

    # ------------------------------------------------------------------ wiring

    def attach(self, server, wire_outbound=False, port_attr="send_update"):
        """Connect a server object for the inbound calls and the query.

        If ``wire_outbound`` is true, set ``server.<port_attr>`` to this
        simulation's outbound port so the server emits through us.
        """
        self.server = server
        if wire_outbound:
            setattr(server, port_attr, self.outbound)
        return self

    def _require_server(self):
        if self.server is None:
            raise RuntimeError("no server attached; call attach(server) first")

    # ---------------------------------------------------------- outbound port

    def _outbound(self, station, price):
        """The send-update port the server invokes to emit an update.

        Captures the emission (observable) and places the update on the
        station-bound channel, where it awaits a delivery step.
        """
        self._update_seq += 1
        self.station_channel.append(Update(self._update_seq, station, price))
        self.sent.append((station, price))
        return None

    # ------------------------------------------------------- explicit drivers

    def _has_submission(self):
        return self._sub_index < len(self._submissions)

    @property
    def pending_submissions(self):
        """Scripted submissions not yet issued, in script order."""
        return list(self._submissions[self._sub_index:])

    def pending_updates(self):
        """Updates currently in flight on the station-bound channel."""
        return list(self.station_channel)

    def pending_acks(self):
        """Acknowledgements currently in flight back to the server."""
        return list(self.ack_channel)

    def fire_submission(self):
        """Issue the next scripted submit-desired-price call on the server."""
        if not self._has_submission():
            raise RuntimeError("no scripted submission remaining")
        self._require_server()
        station, price = self._submissions[self._sub_index]
        self._sub_index += 1
        self.server.submit_desired_price(station, price)
        self.history.append(("submit", station, price))
        return (station, price)

    def deliver(self, seq):
        """Deliver the in-flight update identified by ``seq`` to its station.

        The station then displays that value and emits an acknowledgement onto
        the order-preserving ack channel.
        """
        idx = None
        for i, u in enumerate(self.station_channel):
            if u.seq == seq:
                idx = i
                break
        if idx is None:
            raise ValueError("no in-flight update with seq=%r" % (seq,))
        u = self.station_channel.pop(idx)
        self.displays[u.station] = u.price
        self.delivered.append((u.station, u.price))
        self._ack_seq += 1
        self.ack_channel.append(Ack(self._ack_seq, u.station, u.seq))
        self.history.append(("deliver", u.station, u.price))
        return (u.station, u.price)

    def deliver_ack(self):
        """Deliver the head of the ack channel to the server's inbound port.

        Only the head may be delivered, preserving the global in-order
        guarantee of the acknowledgement channel.
        """
        if not self.ack_channel:
            raise RuntimeError("no acknowledgement in flight")
        self._require_server()
        ack = self.ack_channel.pop(0)
        self.server.acknowledge(ack.station)
        self.acks.append(ack.station)
        self.history.append(("ack", ack.station))
        return ack.station

    # --------------------------------------------------------- seeded driving

    def step(self):
        """Advance one logical step chosen by the seeded scheduler.

        The ready actions are: the next scripted submission (if any), delivery
        of any single in-flight update (reorderable), and delivery of the head
        acknowledgement (order-preserving).  One is chosen uniformly via the
        seeded RNG.  Returns a trace tuple, or ``None`` when quiescent.
        """
        actions = []
        if self._has_submission():
            actions.append(("submit", None))
        for u in self.station_channel:
            actions.append(("deliver", u.seq))
        if self.ack_channel:
            actions.append(("ack", None))

        if not actions:
            return None

        kind, arg = actions[self.random.randrange(len(actions))]
        if kind == "submit":
            return ("submit",) + self.fire_submission()
        if kind == "deliver":
            return ("deliver",) + self.deliver(arg)
        return ("ack", self.deliver_ack())

    def run(self, max_steps=1000000):
        """Drive steps until quiescent: no submission pending, nothing in flight.

        Raises ``RuntimeError`` if the run has not quiesced within
        ``max_steps`` (a guard against an unexpectedly non-terminating server).
        """
        steps = 0
        while True:
            if steps >= max_steps:
                raise RuntimeError("simulation did not quiesce within %d steps"
                                   % (max_steps,))
            if self.step() is None:
                return
            steps += 1

    # -------------------------------------------------------------- observe

    def displayed(self, station):
        """The value a station currently shows, or UNKNOWN if none received."""
        return self.displays.get(station, UNKNOWN)

    def inspect(self, station):
        """Delegate to the server's read-only inspect-station query."""
        self._require_server()
        return self.server.inspect_station(station)

    def in_flight(self):
        """True while any update or acknowledgement is still in transit."""
        return bool(self.station_channel) or bool(self.ack_channel)

    def quiescent(self):
        """True when no submission is pending and nothing is in flight."""
        return (not self._has_submission()
                and not self.station_channel
                and not self.ack_channel)


def random_script(seed, stations, length, price_range=(100, 999)):
    """Build a reproducible scripted submission sequence from a seed.

    Returns a list of (station, price) pairs.  Uses its own Random(seed) so it
    never perturbs a Simulation's scheduler RNG.  The script may repeat a
    station (including bursts) and interleave across stations.
    """
    rng = random.Random(seed)
    stations = list(stations)
    lo, hi = price_range
    script = []
    for _ in range(length):
        script.append((rng.choice(stations), rng.randint(lo, hi)))
    return script
