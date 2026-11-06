"""Tests for GASV3DEV3-22 (requirement GASV3DEV3-5).

Criterion: an update to a station is suppressed EXACTLY when the price to be
sent equals the price that station is already known to display; when the price
differs (including the case where nothing is yet known to be displayed), an
update is sent.

All driving happens through ``nrvv_env`` only.  The server's notion of a
station's *known displayed* price is the price of the most recently
acknowledged update to that station (the acknowledgement is the event through
which the server learns what the station now shows -- GASV3DEV3-13), and since
at most one update per station is outstanding (D2) each acknowledgement
correlates unambiguously to the single update it confirms.
"""

import app
from nrvv_env import Simulation, UNKNOWN, random_script


# --------------------------------------------------------------------------- #
# Construction of the server under test.  The Interface binds every operation
# to a snake_case function/method of ``app``; we locate a server object that
# exposes the inbound operations and query, trying the common factory/class
# shapes and falling back to the module itself.
# --------------------------------------------------------------------------- #

_IFACE = ("submit_desired_price", "acknowledge", "inspect_station")


def _has_iface(obj):
    return all(callable(getattr(obj, name, None)) for name in _IFACE)


def _make_server(sim):
    candidate_names = [
        "Server", "Service", "PriceService", "StationPriceService",
        "StationService", "App", "Application", "Gateway", "PriceGateway",
        "create_server", "make_server", "new_server", "create_service",
        "build_server", "create", "build", "server", "service",
    ]
    tried = []
    for name in candidate_names:
        obj = getattr(app, name, None)
        if obj is None:
            continue
        if not callable(obj):
            if _has_iface(obj):
                return obj
            continue
        for args, kwargs in (
            ((), {}),
            ((sim.outbound,), {}),
            ((), {"send_update": sim.outbound}),
            ((), {"outbound": sim.outbound}),
            ((), {"send_update_port": sim.outbound}),
        ):
            try:
                srv = obj(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - construction probing
                tried.append((name, repr(exc)))
                continue
            if _has_iface(srv):
                return srv
    if _has_iface(app):
        return app
    raise RuntimeError(
        "could not construct an app server exposing %r; tried: %r"
        % (list(_IFACE), tried))


def _fresh(seed, script):
    """Build a simulation with a freshly constructed, wired-up server."""
    sim = Simulation(seed=seed, script=list(script))
    server = _make_server(sim)
    sim.attach(server, wire_outbound=True)
    return sim


def _flush(sim, max_rounds=10000):
    """Deliver every in-flight update and acknowledgement to quiescence,
    WITHOUT firing any further scripted submission.

    After this returns, every update the server has already emitted has been
    delivered and acknowledged, so the server's *known displayed* value for
    each affected station reflects the last update it sent.
    """
    rounds = 0
    while sim.pending_updates() or sim.pending_acks():
        rounds += 1
        if rounds > max_rounds:
            raise AssertionError("flush did not converge")
        for update in sim.pending_updates():
            sim.deliver(update.seq)
        while sim.pending_acks():
            sim.deliver_ack()


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

def test_first_submission_sends_when_display_unknown():
    """Nothing is yet known to be displayed, so the submitted price differs
    from the (unknown) displayed price and an update must be sent."""
    station, price = "S1", 500
    sim = _fresh(seed=3, script=[(station, price)])

    assert sim.sent == []
    sim.fire_submission()
    assert sim.sent == [(station, price)]


def test_no_update_when_equal_to_known_display():
    """Once the station is known to display P, submitting P again sends nothing."""
    station, price = "S1", 742
    sim = _fresh(seed=4, script=[(station, price), (station, price)])

    sim.fire_submission()
    assert sim.sent[-1] == (station, price)
    _flush(sim)  # known displayed price becomes `price`

    before = len(sim.sent)
    sim.fire_submission()  # price equals the known displayed price
    assert len(sim.sent) == before, "redundant update was sent"
    # the suppressed submission left nothing to transmit
    assert sim.pending_updates() == []
    assert sim.pending_acks() == []


def test_suppress_exactly_when_equal_toggle():
    """A single station, alternating equal/different submissions: an update is
    emitted precisely for the submissions whose price differs from what the
    station is currently known to display."""
    s = "S1"
    script = [
        (s, 500),  # unknown  -> differs -> send
        (s, 500),  # known500 -> equal   -> suppress
        (s, 600),  # known500 -> differs -> send
        (s, 600),  # known600 -> equal   -> suppress
        (s, 500),  # known600 -> differs -> send
    ]
    sim = _fresh(seed=7, script=script)

    expectations = [
        (True, (s, 500)),
        (False, None),
        (True, (s, 600)),
        (False, None),
        (True, (s, 500)),
    ]
    for should_send, sent_value in expectations:
        before = len(sim.sent)
        sim.fire_submission()
        if should_send:
            assert len(sim.sent) == before + 1, "expected an update to be sent"
            assert sim.sent[-1] == sent_value
        else:
            assert len(sim.sent) == before, "expected the update to be suppressed"
        _flush(sim)  # settle known displayed value before the next submission


def test_suppression_is_per_station():
    """Suppression is keyed to each station's own known displayed price."""
    a, b = "A", "B"
    script = [(a, 100), (b, 100), (a, 100), (b, 200)]
    sim = _fresh(seed=11, script=script)

    sim.fire_submission()  # A: unknown -> 100 -> send
    _flush(sim)
    sim.fire_submission()  # B: unknown -> 100 -> send
    _flush(sim)

    before = len(sim.sent)
    sim.fire_submission()  # A: 100 equals A's known display -> suppress
    assert len(sim.sent) == before
    _flush(sim)

    before = len(sim.sent)
    sim.fire_submission()  # B: 200 differs from B's known display -> send
    assert len(sim.sent) == before + 1
    assert sim.sent[-1] == (b, 200)


def test_no_sent_update_ever_equals_known_displayed_random():
    """Across randomized, interleaved runs the server never emits an update
    whose price equals the station's current known displayed price (the
    suppression direction), while every targeted final value is in fact sent
    (the 'sent when different' direction).
    """
    stations = ["A", "B", "C"]
    for seed in (0, 1, 2, 3, 5):
        script = random_script(seed, stations, length=40)
        sim = _fresh(seed=seed, script=script)

        known = {}        # station -> price the server is known to display
        outstanding = {}  # station -> price of the single unacked update

        steps = 0
        while True:
            sent_len = len(sim.sent)
            trace = sim.step()
            if trace is None:
                break
            steps += 1
            assert steps < 100000, "simulation failed to quiesce"

            # An acknowledgement teaches the server the station now displays the
            # value of its single outstanding update; apply that before
            # inspecting any update the same step may have triggered.
            if trace[0] == "ack":
                st = trace[1]
                if st in outstanding:
                    known[st] = outstanding.pop(st)

            for (st, price) in sim.sent[sent_len:]:
                assert known.get(st, UNKNOWN) != price, (
                    "update to %r carried %r which equals its known "
                    "displayed price" % (st, price))
                outstanding[st] = price

        # Positive direction: every station's last desired value was actually
        # emitted at some point (it could only become 'known displayed' via a
        # send), confirming updates are sent when the value differs.
        last_desired = {}
        for (st, price) in script:
            last_desired[st] = price
        for st, price in last_desired.items():
            assert (st, price) in sim.sent
