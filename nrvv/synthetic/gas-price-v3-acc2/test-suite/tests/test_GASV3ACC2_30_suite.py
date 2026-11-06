"""Suite for TEST_CASE GASV3ACC2-30 (requirement GASV3ACC2-12).

Criterion: for a single station, while sending is not yet permitted (an update
is outstanding), submitting a sequence of distinct desired prices (p1, p2, p3)
must coalesce by *overwriting* the single latest-desired slot. When sending next
becomes permissible, exactly one price is sent and it is the last submitted
price (p3); the earlier intermediate prices are never sent individually.

Everything is driven through the supplied environment ``nrvv_env`` and observed
through its transmit log, station models and the server's get-station-state.
Runs are fully deterministic: the environment's atomic actions are selected
explicitly (no clock, no threads, and no reliance on RNG ordering).
"""

import app
import nrvv_env


# --------------------------------------------------------------------------
# wiring: obtain a server whose outbound transmit port is `transmit`
# --------------------------------------------------------------------------

_OPS = ("submit_desired_price", "acknowledgement_received", "get_station_state")


def _has_ops(obj):
    return all(callable(getattr(obj, name, None)) for name in _OPS)


def _candidate_constructors(mod):
    for name in ("Server", "PriceServer", "ReconciliationServer", "Reconciler",
                 "Coalescer", "GasServer", "App", "Service", "Hub", "Core"):
        c = getattr(mod, name, None)
        if c is not None:
            yield c
    for name in ("create_server", "make_server", "build_server", "new_server",
                 "server", "build", "create", "make", "new"):
        f = getattr(mod, name, None)
        if callable(f):
            yield f


def _wire_transmit(obj, transmit):
    for setter in ("set_transmit", "bind_transmit", "set_transmit_port",
                   "on_transmit", "configure", "wire", "bind"):
        s = getattr(obj, setter, None)
        if callable(s):
            try:
                s(transmit)
                return True
            except TypeError:
                try:
                    s(transmit=transmit)
                    return True
                except TypeError:
                    pass
    for attr in ("transmit", "transmit_port", "emit", "send", "on_emit", "sink"):
        if hasattr(obj, attr):
            try:
                setattr(obj, attr, transmit)
                return True
            except Exception:
                pass
    return False


def _make_server(transmit):
    """Factory passed to ``Simulation.connect``; builds the server wired to the
    environment's outbound transmit port, discovering the construction style the
    environment documents (``app.Server(sim.transmit)``) with tolerant fallbacks.
    """
    for ctor in _candidate_constructors(app):
        for build in (lambda: ctor(transmit), lambda: ctor(transmit=transmit)):
            try:
                srv = build()
            except TypeError:
                continue
            except Exception:
                continue
            if _has_ops(srv):
                return srv
        try:
            srv = ctor()
        except Exception:
            srv = None
        if srv is not None and _has_ops(srv):
            _wire_transmit(srv, transmit)
            return srv
    if _has_ops(app):
        _wire_transmit(app, transmit)
        return app
    raise RuntimeError(
        "could not construct an `app` server exposing %r" % (list(_OPS),))


# --------------------------------------------------------------------------
# deterministic driving of the environment's atomic actions
# --------------------------------------------------------------------------

def _perform(sim, kind, station):
    """Perform the one currently-available environment action of `kind` for
    `station`, using the simulation's own action machinery (so the real server
    operations, transport and station models all run). Deterministic.
    """
    for action in sim._available_actions():
        if action[0] != kind:
            continue
        who = action[1] if kind == "submit" else action[1].station
        if who == station:
            return sim._perform(action)
    raise AssertionError(
        "no %r action for station %r; available=%r"
        % (kind, station, sim._available_actions()))


def _sent_to(sim, station):
    return [p for (s, p) in sim.sent if s == station]


def _state_values(state):
    if isinstance(state, dict):
        return list(state.values())
    asdict = getattr(state, "_asdict", None)
    if callable(asdict):
        return list(asdict().values())
    try:
        return list(state)
    except TypeError:
        pass
    vals = []
    for name in dir(state):
        if name.startswith("_"):
            continue
        v = getattr(state, name)
        if not callable(v):
            vals.append(v)
    return vals


# --------------------------------------------------------------------------
# tests
# --------------------------------------------------------------------------

def test_only_last_price_sent_when_sending_becomes_permissible():
    S = "S0"
    p0, p1, p2, p3 = 10, 20, 30, 40
    sim = nrvv_env.Simulation([(S, p0), (S, p1), (S, p2), (S, p3)], seed=0)
    sim.connect(_make_server)

    # First desired price: station idle + diverged -> emitted immediately,
    # so now an update is outstanding (sending is not yet permitted).
    _perform(sim, "submit", S)
    assert _sent_to(sim, S) == [p0]

    # While outstanding, submit the distinct sequence p1, p2, p3. Each must only
    # overwrite the latest-desired slot; none may be sent individually.
    _perform(sim, "submit", S)      # p1
    _perform(sim, "submit", S)      # p2
    _perform(sim, "submit", S)      # p3
    assert _sent_to(sim, S) == [p0]

    # Make sending permissible: deliver and acknowledge the outstanding update.
    _perform(sim, "deliver", S)     # delivery alone must not emit anything
    assert _sent_to(sim, S) == [p0]
    _perform(sim, "ack", S)         # ack permits the next (coalesced) send

    # Exactly one new send, carrying the last submitted price; p1/p2 never sent.
    sent = _sent_to(sim, S)
    assert sent == [p0, p3]
    assert sent.count(p3) == 1
    assert p1 not in sent
    assert p2 not in sent

    # Drain the transport; nothing further is emitted and the station settles.
    sim.run()
    assert _sent_to(sim, S) == [p0, p3]
    assert sim.applied(S) == p3


def test_intermediate_submits_add_no_sends_while_outstanding():
    S = "alpha"
    prices = [5, 15, 25, 35, 45]   # one initial price, then four intermediates
    sim = nrvv_env.Simulation([(S, p) for p in prices], seed=1)
    sim.connect(_make_server)

    _perform(sim, "submit", S)                  # initial emission -> outstanding
    assert _sent_to(sim, S) == [prices[0]]

    # Every subsequent submit (an update still outstanding) overwrites the slot
    # and adds no new transmission: the send count stays at exactly one.
    for _ in prices[1:]:
        _perform(sim, "submit", S)
        assert _sent_to(sim, S) == [prices[0]]

    # Becoming permissible sends only the current latest-desired value (the last).
    _perform(sim, "deliver", S)
    _perform(sim, "ack", S)
    sent = _sent_to(sim, S)
    assert sent == [prices[0], prices[-1]]
    for intermediate in prices[1:-1]:
        assert intermediate not in sent


def test_latest_desired_slot_is_overwritten_not_accumulated():
    S = "beta"
    p0, p1, p2, p3 = 100, 7, 42, 99
    sim = nrvv_env.Simulation([(S, p0), (S, p1), (S, p2), (S, p3)], seed=2)
    sim.connect(_make_server)

    _perform(sim, "submit", S)      # p0 -> outstanding
    _perform(sim, "submit", S)      # p1 overwrites
    _perform(sim, "submit", S)      # p2 overwrites
    _perform(sim, "submit", S)      # p3 overwrites

    # Only one latest-desired record is retained, holding the last value (p3);
    # the superseded intermediate prices are not kept anywhere in the state.
    vals = _state_values(sim.get_station_state(S))
    assert p3 in vals
    assert p1 not in vals
    assert p2 not in vals

    # No emission occurred for the coalesced batch while the update was outstanding.
    assert _sent_to(sim, S) == [p0]

    _perform(sim, "deliver", S)
    _perform(sim, "ack", S)
    assert _sent_to(sim, S) == [p0, p3]

    sim.run()
    assert _sent_to(sim, S) == [p0, p3]
    assert sim.applied(S) == p3


def test_coalescing_overwrites_per_station_independently():
    A, B = "A", "B"
    # Interleaved: each station gets an initial price, then intermediates.
    events = [(A, 1), (B, 2),
              (A, 10), (B, 20),
              (A, 11), (B, 21),
              (A, 12), (B, 22)]
    sim = nrvv_env.Simulation(events, seed=3)
    sim.connect(_make_server)

    for station in (A, B, A, B, A, B, A, B):
        _perform(sim, "submit", station)

    # One outstanding send each; intermediates coalesced, none sent yet.
    assert _sent_to(sim, A) == [1]
    assert _sent_to(sim, B) == [2]

    # Permit A only: exactly A's last desired is sent; B is untouched.
    _perform(sim, "deliver", A)
    _perform(sim, "ack", A)
    assert _sent_to(sim, A) == [1, 12]
    assert _sent_to(sim, B) == [2]

    # Permit B: exactly B's last desired is sent.
    _perform(sim, "deliver", B)
    _perform(sim, "ack", B)
    assert _sent_to(sim, B) == [2, 22]

    sim.run()
    assert _sent_to(sim, A) == [1, 12]
    assert _sent_to(sim, B) == [2, 22]
    assert sim.applied(A) == 12
    assert sim.applied(B) == 22
