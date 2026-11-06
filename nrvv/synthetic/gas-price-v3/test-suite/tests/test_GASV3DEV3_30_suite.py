"""Tests for GASV3DEV3-30.

Criterion: with a station that has never acknowledged any update, dispatching a
desired price always sends it (unknown 'displayed' cannot suppress). After an
update is acknowledged, 'displayed' equals that acknowledged price; then a
desired price for an idle station whose value equals 'displayed' is suppressed
(obligation treated as met), and likewise a pending price flushed after an
acknowledgement that equals 'displayed' is suppressed. When the value to send
differs from 'displayed' (or 'displayed' is unknown), the price is sent.

Every test drives the real ``app`` server only through ``nrvv_env``: the
environment's outbound ``send-update`` port and its explicit, seeded drivers.
"""

import nrvv_env
from nrvv_env import Simulation, random_script, UNKNOWN


# --------------------------------------------------------------------------
# Construct the real app server and wire the real outbound port through the
# environment.  No fake/stub/mock of the system is introduced here; this only
# locates and instantiates whatever shape ``app`` exposes its operations in.
# --------------------------------------------------------------------------

_OPS = ("submit_desired_price", "acknowledge", "inspect_station")


def _has_ops(obj):
    return all(hasattr(obj, name) for name in _OPS)


def _try_make(obj, sim):
    attempts = [
        ((sim.outbound,), {}),
        ((), {"send_update": sim.outbound}),
        ((), {"outbound": sim.outbound}),
        ((), {}),
    ]
    for args, kwargs in attempts:
        try:
            result = obj(*args, **kwargs)
        except Exception:
            continue
        return result
    return None


def new_server(sim):
    """Build the real ``app`` server, wire outbound, attach to ``sim``."""
    import app

    server = None

    # 1) An explicit factory or server type, by conventional name.
    for fname in ("create_server", "make_server", "new_server", "build_server",
                  "create_app", "make_app", "Server", "server"):
        obj = getattr(app, fname, None)
        if obj is None:
            continue
        if _has_ops(obj) and not isinstance(obj, type):
            server = obj
            break
        candidate = _try_make(obj, sim)
        if candidate is not None and _has_ops(candidate):
            server = candidate
            break

    # 2) Any CapWords class carrying the operations.
    if server is None:
        for name in dir(app):
            if not name[:1].isupper():
                continue
            obj = getattr(app, name)
            if isinstance(obj, type) and _has_ops(obj):
                candidate = _try_make(obj, sim)
                if candidate is not None and _has_ops(candidate):
                    server = candidate
                    break

    # 3) The module itself exposes the operations as functions.
    if server is None and _has_ops(app):
        server = app

    assert server is not None and _has_ops(server), "cannot construct app server"
    sim.attach(server, wire_outbound=True)
    return server


def _only_seq(sim):
    """The seq of the single in-flight update (asserts exactly one)."""
    updates = sim.pending_updates()
    assert len(updates) == 1, "expected exactly one outstanding update, got %r" % (updates,)
    return updates[0].seq


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def test_first_update_to_unacked_station_is_always_sent():
    # Unknown 'displayed' cannot suppress: an idle, never-acknowledged station
    # always receives its first desired price, whatever the value.
    for i, price in enumerate((100, 500, 999)):
        station = "first_%d" % i
        sim = Simulation(seed=i, script=[(station, price)])
        new_server(sim)
        sim.fire_submission()
        assert sim.sent == [(station, price)]


def test_equal_price_after_ack_on_idle_is_suppressed():
    # After acknowledgement, 'displayed' == acked price; a later desired price
    # for the idle station equal to 'displayed' sends nothing.
    station = "idle_equal"
    sim = Simulation(seed=2, script=[(station, 500), (station, 500)])
    new_server(sim)

    sim.fire_submission()                 # unknown displayed -> send 500
    assert sim.sent == [(station, 500)]
    sim.deliver(_only_seq(sim))           # station physically shows 500, ack queued
    sim.deliver_ack()                     # server now knows displayed == 500
    assert sim.sent == [(station, 500)]

    sim.fire_submission()                 # desired 500 == displayed -> suppress
    assert sim.sent == [(station, 500)]   # nothing new emitted
    assert sim.pending_updates() == []    # obligation met: no new update in flight


def test_different_price_after_ack_on_idle_is_sent():
    # After acknowledgement, a desired price for the idle station that differs
    # from 'displayed' is sent.
    station = "idle_diff"
    sim = Simulation(seed=3, script=[(station, 500), (station, 700)])
    new_server(sim)

    sim.fire_submission()                 # send 500
    sim.deliver(_only_seq(sim))
    sim.deliver_ack()                     # displayed == 500
    assert sim.sent == [(station, 500)]

    sim.fire_submission()                 # 700 != 500 -> send
    assert sim.sent == [(station, 500), (station, 700)]


def test_flush_pending_different_from_displayed_is_sent():
    # A pending price flushed after an acknowledgement that differs from
    # 'displayed' is sent.
    station = "flush_diff"
    sim = Simulation(seed=4, script=[(station, 500), (station, 700)])
    new_server(sim)

    sim.fire_submission()                 # send 500, now outstanding
    sim.fire_submission()                 # 700 arrives while outstanding -> pending
    assert sim.sent == [(station, 500)]   # single-outstanding: nothing new yet

    sim.deliver(_only_seq(sim))           # deliver the 500 update
    sim.deliver_ack()                     # displayed == 500; flush pending 700 != 500 -> send
    assert sim.sent == [(station, 500), (station, 700)]


def test_flush_pending_equal_to_displayed_is_suppressed():
    # A pending price flushed after an acknowledgement that equals 'displayed'
    # sends nothing.
    station = "flush_equal"
    sim = Simulation(seed=5, script=[(station, 500), (station, 700), (station, 500)])
    new_server(sim)

    sim.fire_submission()                 # send 500, outstanding
    sim.fire_submission()                 # pending 700
    sim.fire_submission()                 # latest desired 500 -> pending 500
    assert sim.sent == [(station, 500)]

    sim.deliver(_only_seq(sim))           # deliver the 500 update
    sim.deliver_ack()                     # displayed == 500; flush pending 500 == 500 -> suppress
    assert sim.sent == [(station, 500)]   # nothing new emitted
    assert sim.pending_updates() == []    # obligation met: no new update in flight


def test_unknown_before_ack_does_not_suppress_pending_flush():
    # While no acknowledgement has arrived the displayed value stays unknown and
    # cannot suppress: a differing value submitted while an update is in flight
    # is held as pending and is sent once the first update is acknowledged.
    station = "unknown_flush"
    sim = Simulation(seed=6, script=[(station, 400), (station, 650)])
    new_server(sim)

    sim.fire_submission()                 # send 400
    sim.deliver(_only_seq(sim))           # physically shown, but no ack yet
    sim.fire_submission()                 # 650 while still unacknowledged -> pending
    assert sim.sent == [(station, 400)]   # displayed unknown, but single-outstanding holds

    sim.deliver_ack()                     # ack of 400 -> displayed 400; flush 650 != 400 -> send
    assert sim.sent == [(station, 400), (station, 650)]


def test_suppression_preserves_convergence_under_random_schedules():
    # Across seeded random schedules, suppression of equal-to-displayed values
    # never prevents convergence: every station ends displaying its last desired
    # price, with nothing outstanding or pending.
    for seed in range(5):
        stations = ["conv_%d_%d" % (seed, k) for k in range(3)]
        script = random_script(seed, stations, 12)
        sim = Simulation(seed=seed, script=script)
        new_server(sim)
        sim.run()

        assert sim.quiescent()
        assert len(sim.sent) >= 1

        last_desired = {}
        for st, pr in script:
            last_desired[st] = pr
        for st, pr in last_desired.items():
            assert sim.displayed(st) == pr
