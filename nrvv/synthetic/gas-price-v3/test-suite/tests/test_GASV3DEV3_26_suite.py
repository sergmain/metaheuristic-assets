"""Suite for GASV3DEV3-26: the single-outstanding gate.

These tests drive the server (``app``) only through the simulated environment
(``nrvv_env``).  The server emits updates through the outbound ``send-update``
port, which the simulation observes into ``sim.sent`` (one (station, price) per
emission, in order).  Dispatch is therefore observed as growth of ``sim.sent``.

The environment offers no separate \"server tick\": the only moments the server
can act are during an inbound call it receives, i.e. a scripted submission
(``fire_submission`` -> ``submit_desired_price``) or an acknowledgement
(``deliver_ack`` -> ``acknowledge``).  Any dispatch is thus synchronous within
such a call and visible in ``sim.sent`` immediately afterwards.
"""

from collections import Counter

import app
from nrvv_env import Simulation, random_script


_SERVER_METHODS = ("submit_desired_price", "acknowledge", "inspect_station")


def _is_server(obj):
    return all(callable(getattr(obj, name, None)) for name in _SERVER_METHODS)


def _new_server(port):
    """Obtain a fresh server object from ``app``.

    Tries the common factory/class names, with and without the outbound port
    injected positionally; falls back to the module itself if it exposes the
    inbound interface directly.  The outbound port is (re)wired by the caller
    via ``attach(..., wire_outbound=True)`` regardless.
    """
    for name in ("Server", "GasServer", "PriceServer", "Gateway",
                 "make_server", "create_server", "new_server", "build_server"):
        factory = getattr(app, name, None)
        if factory is None:
            continue
        for args in ((), (port,)):
            try:
                candidate = factory(*args)
            except TypeError:
                continue
            except Exception:
                continue
            if _is_server(candidate):
                return candidate
    if _is_server(app):
        return app
    raise RuntimeError("cannot construct a server object from app")


def _make(seed=0, script=None):
    sim = Simulation(seed=seed, script=list(script) if script else [])
    server = _new_server(sim.outbound)
    sim.attach(server, wire_outbound=True, port_attr="send_update")
    return sim


def test_clear_gate_dispatches_immediately():
    # outstanding? is clear at the start, so one desired price -> exactly one
    # update dispatched immediately.
    station = "CLEAR-1"
    sim = _make(script=[(station, 100)])
    sim.fire_submission()
    assert sim.sent == [(station, 100)]


def test_outstanding_blocks_any_number_of_further_prices():
    # After the first dispatch sets outstanding?, no number of further desired
    # prices for the same station may cause another dispatch.
    station = "BLOCK-1"
    sim = _make(script=[(station, 100), (station, 200), (station, 300),
                        (station, 400), (station, 500)])
    sim.fire_submission()                      # 100 -> dispatched
    assert sim.sent == [(station, 100)]
    for _ in range(4):                          # 200, 300, 400, 500
        sim.fire_submission()
    # Still exactly the one update; the gate held across every submission.
    assert sim.sent == [(station, 100)]
    # And exactly one update is actually in flight to that station.
    assert len(sim.pending_updates()) == 1


def test_delivery_alone_does_not_dispatch_or_unblock():
    # Delivering the update to the station (without the ack reaching the
    # server) must not dispatch anything new, nor clear the gate.
    station = "DELIV-1"
    sim = _make(script=[(station, 100), (station, 200)])
    sim.fire_submission()                      # 100 -> dispatched
    seq = sim.pending_updates()[0].seq
    sim.deliver(seq)                            # station displays 100; ack queued
    assert sim.sent == [(station, 100)]         # delivery dispatched nothing
    sim.fire_submission()                      # 200 arrives, gate still set
    assert sim.sent == [(station, 100)]         # still blocked (ack not learned)


def test_ack_reenables_next_price_exactly_one_update():
    # With no pending price outstanding at ack time, the acknowledgement clears
    # the gate; the *next* desired price then causes exactly one new update.
    station = "ACK-1"
    sim = _make(script=[(station, 100), (station, 200)])
    sim.fire_submission()                      # 100 -> dispatched
    assert sim.sent == [(station, 100)]
    seq = sim.pending_updates()[0].seq
    sim.deliver(seq)                            # deliver -> ack queued
    sim.deliver_ack()                           # acknowledge(station) -> gate clears
    # Nothing was pending, so the ack itself dispatches nothing new.
    before = len(sim.sent)
    sim.fire_submission()                      # 200 after ack -> one new update
    assert len(sim.sent) == before + 1
    assert sim.sent[-1] == (station, 200)


def test_full_sequence_at_most_one_flushed_on_ack():
    # Full narrative: dispatch, then several blocked prices, then ack.  After
    # the ack the gate is clear; an implementation may flush the latest pending
    # price, but it may dispatch AT MOST one update and it must carry the
    # latest desired value.  Never two updates while the first is unacked.
    station = "FULL-1"
    sim = _make(script=[(station, 10), (station, 20), (station, 30)])
    sim.fire_submission()                      # 10 -> dispatched
    assert sim.sent == [(station, 10)]
    sim.fire_submission()                      # 20 -> blocked
    sim.fire_submission()                      # 30 -> blocked
    assert sim.sent == [(station, 10)]          # gate held across both
    seq = sim.pending_updates()[0].seq
    sim.deliver(seq)
    assert sim.sent == [(station, 10)]          # delivery dispatches nothing
    before = len(sim.sent)
    sim.deliver_ack()                           # gate clears
    after = len(sim.sent)
    assert after in (before, before + 1)        # at most one flushed
    if after == before + 1:
        assert sim.sent[-1] == (station, 30)    # and it is the latest desired


def test_gate_is_per_station():
    # The gate is per station: an update outstanding to A must not block a
    # first dispatch to a different station B, yet A itself stays blocked.
    a, b = "PS-A", "PS-B"
    sim = _make(script=[(a, 100), (b, 200), (a, 300)])
    sim.fire_submission()                      # A 100 -> dispatched
    assert sim.sent == [(a, 100)]
    sim.fire_submission()                      # B 200 -> dispatched (B clear)
    assert sim.sent == [(a, 100), (b, 200)]
    sim.fire_submission()                      # A 300 -> blocked (A outstanding)
    assert sim.sent == [(a, 100), (b, 200)]


def test_single_outstanding_invariant_under_random_schedules():
    # Property, across several seeds and random schedules: at every observable
    # moment the number of updates dispatched to a station never exceeds the
    # number of acknowledgements learned for it by more than one -- i.e. there
    # is never more than one unacknowledged update outstanding per station.
    for seed in (0, 1, 2, 3, 7, 11):
        stations = ["R%d_%d" % (seed, i) for i in range(3)]
        script = random_script(seed, stations, length=40)
        sim = _make(seed=seed, script=script)
        while True:
            if sim.step() is None:
                break
            sent = Counter(st for st, _ in sim.sent)
            acked = Counter(sim.acks)
            for st in stations:
                assert sent[st] - acked[st] <= 1
