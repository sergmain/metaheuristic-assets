"""Suite for TEST_CASE GASV3ACC2-29.

Criterion: an update to a station is treated as *received* only once that
station's acknowledgement for it arrives.  Before the ack it must read as
not-yet-received; once the ack arrives it is marked received.  Because
acknowledgements come back in send order, the Nth ack marks the Nth sent
update as received, and no update is treated as received before the ack for
every earlier update has been received.

The server (`app`) is driven exclusively through the `nrvv_env` simulation:
its outbound transmit port is wired to the simulation, the simulation fires
inbound operations (submit-desired-price, acknowledgement-received), and the
server's reconciliation state is observed through get-station-state
(GASV3ACC2-19).  Nothing else is faked or mocked.
"""

import app
import nrvv_env


# --------------------------------------------------------------------------
# Wiring helpers: construct and wire the server to the simulation's outbound
# transmit port, tolerating either a Server class or module-level operations.
# --------------------------------------------------------------------------

class _ModuleServer(object):
    """Adapts module-level operations of `app` to the object shape the
    simulation drives."""

    def submit_desired_price(self, station, price):
        return app.submit_desired_price(station, price)

    def acknowledgement_received(self, station):
        return app.acknowledgement_received(station)

    def get_station_state(self, station):
        return app.get_station_state(station)


def _connect(sim):
    """Build and bind the server with its transmit port wired to `sim`."""
    Server = getattr(app, "Server", None)
    if Server is not None:
        try:
            return sim.connect(Server)
        except TypeError:
            pass
    for name in ("set_transmit", "set_transmit_port", "configure",
                 "connect", "bind", "wire", "setup", "init"):
        fn = getattr(app, name, None)
        if callable(fn):
            try:
                fn(sim.transmit)
                break
            except TypeError:
                continue
    srv = _ModuleServer()
    sim.bind(srv)
    return srv


# --------------------------------------------------------------------------
# State extraction: get-station-state returns
#   { latest desired price, last acknowledged price value, outstanding flag }.
# We locate the "last acknowledged" value and the "outstanding" flag without
# assuming an exact field spelling or container shape.
# --------------------------------------------------------------------------

_MISSING = object()


def _find(items, needles):
    for key, value in items.items():
        low = str(key).lower()
        for needle in needles:
            if needle in low:
                return value
    return _MISSING


def _probe(obj, names):
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return _MISSING


def _extract(state):
    """Return (last_acknowledged, outstanding) from a station-state reading."""
    items = None
    if isinstance(state, dict):
        items = state
    elif hasattr(state, "_asdict"):
        items = state._asdict()
    elif hasattr(state, "__dict__") and vars(state):
        items = vars(state)

    if items is not None:
        acked = _find(items, ("acknowledg", "ack"))
        outstanding = _find(items, ("outstand", "pending", "in_flight",
                                    "inflight", "flight"))
    else:
        acked = _probe(state, ("last_acknowledged", "last_acked",
                               "acknowledged", "last_ack", "acked"))
        outstanding = _probe(state, ("outstanding", "has_outstanding",
                                     "is_outstanding", "pending",
                                     "in_flight", "inflight"))
        if acked is _MISSING and isinstance(state, (tuple, list)) \
                and len(state) >= 3:
            acked, outstanding = state[1], state[2]

    assert acked is not _MISSING, "no last-acknowledged field in %r" % (state,)
    assert outstanding is not _MISSING, "no outstanding field in %r" % (state,)
    return acked, outstanding


# --------------------------------------------------------------------------
# Shared invariant tying server-observed receipt state to the environment's
# per-station send and acknowledgement logs.
# --------------------------------------------------------------------------

def _by_station(log, station):
    return [price for (st, price) in log if st == station]


def _assert_receipt_invariant(sim, server):
    """At any quiescent-between-steps moment, for each station:

      * acknowledgements form a send-order prefix of the sends (so the Nth ack
        corresponds to the Nth sent update);
      * the server's last-acknowledged mirror equals the most recent acked
        value (None before any ack);
      * the outstanding flag is set exactly while a sent update awaits its ack,
        i.e. an in-flight update is reported not-yet-received.
    """
    for station in set(st for st, _ in sim.sent):
        sent = _by_station(sim.sent, station)
        acked = _by_station(sim.acknowledged, station)

        # Acks match sends in order: the Nth ack is for the Nth sent update.
        assert acked == sent[:len(acked)], (station, sent, acked)

        last_ack, outstanding = _extract(server.get_station_state(station))

        if acked:
            assert last_ack == acked[-1], (station, last_ack, acked)
        else:
            assert last_ack is None, (station, last_ack)

        # Outstanding iff an emitted update is still awaiting acknowledgement.
        assert bool(outstanding) == (len(sent) > len(acked)), \
            (station, outstanding, sent, acked)

        # While an update is in flight, strictly fewer are received than sent:
        # the in-flight one is not yet counted as received.
        if outstanding:
            assert len(acked) < len(sent), (station, sent, acked)


SEEDS = (1, 7, 42, 100, 1234, 2024)


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def test_inflight_update_reported_not_received():
    """The first emitted update, before its ack returns, is outstanding and
    the last-acknowledged mirror is still unset: not yet received."""
    sim = nrvv_env.Simulation.from_seed(1234)
    server = _connect(sim)

    # Drive until the server emits its first update (and nothing else yet).
    while not sim.sent:
        assert sim.step() is not None
    station, _price = sim.sent[0]

    # No acknowledgement has come back for it.
    assert all(st != station for st, _ in sim.acknowledged)

    last_ack, outstanding = _extract(server.get_station_state(station))
    assert bool(outstanding) is True
    assert last_ack is None


def test_update_marked_received_only_when_its_ack_arrives():
    """A sent update flips from not-received to received exactly at its ack,
    and that first ack corresponds to the first sent update."""
    sim = nrvv_env.Simulation.from_seed(2024)
    server = _connect(sim)

    while not sim.sent:
        assert sim.step() is not None
    station, first_price = sim.sent[0]

    # Before the ack: not received.
    last_ack, outstanding = _extract(server.get_station_state(station))
    assert last_ack is None
    assert bool(outstanding) is True

    # Advance until the first acknowledgement for this station returns.
    while not any(st == station for st, _ in sim.acknowledged):
        assert sim.step() is not None

    # The first ack matches the first sent update (send-order matching),
    # and the server now mirrors that value as received.
    first_ack_price = next(p for st, p in sim.acknowledged if st == station)
    assert first_ack_price == first_price
    last_ack, _ = _extract(server.get_station_state(station))
    assert last_ack == first_price


def test_nth_ack_marks_nth_sent_update_in_send_order():
    """Across whole seeded runs, after every step the acknowledgements are a
    send-order prefix of the sends and the mirror tracks the latest ack."""
    for seed in SEEDS:
        sim = nrvv_env.Simulation.from_seed(seed)
        server = _connect(sim)
        _assert_receipt_invariant(sim, server)
        while sim.step() is not None:
            _assert_receipt_invariant(sim, server)


def test_update_never_received_before_earlier_acks():
    """No update is treated as received before the ack for every earlier
    update has been received: received count never exceeds, and always equals
    a prefix of, the acknowledged-in-order stream."""
    for seed in SEEDS:
        sim = nrvv_env.Simulation.from_seed(seed)
        server = _connect(sim)
        while sim.step() is not None:
            for station in set(st for st, _ in sim.sent):
                sent = _by_station(sim.sent, station)
                acked = _by_station(sim.acknowledged, station)
                # Received updates are a contiguous send-order prefix: an update
                # is received only after all earlier ones are.
                assert acked == sent[:len(acked)], (station, sent, acked)
                last_ack, _ = _extract(server.get_station_state(station))
                if acked:
                    assert last_ack == acked[-1], (station, last_ack, acked)
                else:
                    assert last_ack is None, (station, last_ack)


def test_all_updates_received_after_quiescence():
    """Once every ack has returned, each station has every sent update marked
    received (mirror at the last sent value) and nothing outstanding."""
    for seed in SEEDS:
        sim = nrvv_env.Simulation.from_seed(seed)
        server = _connect(sim)
        sim.run()
        assert sim.quiescent()
        for station in set(st for st, _ in sim.sent):
            sent = _by_station(sim.sent, station)
            acked = _by_station(sim.acknowledged, station)
            assert acked == sent, (station, sent, acked)
            last_ack, outstanding = _extract(server.get_station_state(station))
            assert bool(outstanding) is False, (station, outstanding)
            assert last_ack == sent[-1], (station, last_ack, sent)
