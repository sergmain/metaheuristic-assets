"""Suite for TMPGASDF1-25 / requirement TMPGASDF1-8.

Criterion: when a station's known-displayed price has been set to P *solely by a
prior acknowledgement*, setting (or re-evaluating, on acknowledgement) a desired
price equal to P sends no update; a desired price that differs from the confirmed
known-displayed value does send one. Known-displayed advances only in response to
an acknowledgement, never from an unconfirmed guess, so a genuinely different
desired price is never wrongly suppressed.

Every test drives ``app`` only through ``nrvv_env``. The seeded script is disabled
(``num_bursts=0``) so the run is driven entirely by deterministic manual injection
and by stepping the transport when only one action is possible (which makes
``step`` deterministic regardless of seed).
"""
import app
from nrvv_env import Simulation


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _build(seed=1234):
    """A quiescent simulation with no seeded script, wired to a fresh server."""
    sim = Simulation(seed, num_stations=4, num_bursts=0)
    server = app.Service(sim.send_update)
    sim.connect(server)
    return sim, server


def _field(view, *needles):
    """Read a field from an ``inspect`` result tolerant of exact key spelling.

    Matches a key whose lowercased, punctuation-stripped form contains every
    needle (e.g. ('known', 'display') -> 'known_displayed'/'known-displayed').
    """
    pairs = []
    if isinstance(view, dict):
        pairs = list(view.items())
    else:
        for k in dir(view):
            if k.startswith("_"):
                continue
            try:
                pairs.append((k, getattr(view, k)))
            except Exception:
                pass
    for k, v in pairs:
        if callable(v):
            continue
        kl = str(k).lower().replace("-", "").replace("_", "")
        if all(n in kl for n in needles):
            return v
    raise AssertionError("no field %r in %r" % (needles, view))


def _known_displayed(server, sid):
    return _field(server.inspect(sid), "known", "display")


def _latest_desired(server, sid):
    return _field(server.inspect(sid), "latest")


def _outstanding(server, sid):
    return _field(server.inspect(sid), "outstanding")


def _sends_for(sim, sid):
    return [r for r in sim.send_log if r.station == sid]


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------
def test_desired_equal_to_acked_known_displayed_sends_nothing():
    """After an ack sets known-displayed to P, re-setting desired to P sends no
    update; the service stays converged and quiescent."""
    sim, server = _build(seed=1)
    sid = "S0"

    sim.inject_desired(sid, 5)            # first desired for a blank station -> send
    assert len(_sends_for(sim, sid)) == 1
    assert _sends_for(sim, sid)[0].price == 5

    sim.run()                             # deliver update, deliver ack
    assert _known_displayed(server, sid) == 5
    assert _outstanding(server, sid) is None
    sends_after_ack = len(_sends_for(sim, sid))

    # Desired equals the acknowledged known-displayed value: must suppress.
    sim.inject_desired(sid, 5)
    assert len(_sends_for(sim, sid)) == sends_after_ack

    # Re-evaluation produces nothing in flight and no further send.
    assert sim.run() == 0
    assert len(_sends_for(sim, sid)) == sends_after_ack
    assert _known_displayed(server, sid) == 5
    assert _latest_desired(server, sid) == 5
    assert _outstanding(server, sid) is None
    assert sim.displayed(sid) == 5


def test_desired_differing_from_known_displayed_sends_update():
    """A desired price different from the confirmed known-displayed value is sent."""
    sim, server = _build(seed=2)
    sid = "S1"

    sim.inject_desired(sid, 5)
    sim.run()
    assert _known_displayed(server, sid) == 5
    base = len(_sends_for(sim, sid))

    sim.inject_desired(sid, 8)            # 8 != known-displayed 5 -> must send
    sends = _sends_for(sim, sid)
    assert len(sends) == base + 1
    assert sends[-1].price == 8

    sim.run()
    assert _known_displayed(server, sid) == 8
    assert _outstanding(server, sid) is None
    assert sim.displayed(sid) == 8


def test_known_displayed_advances_only_on_acknowledgement_not_on_guess():
    """Known-displayed stays None after the update is sent and even after the
    station physically displays it; it becomes P only once the acknowledgement
    reaches the service."""
    sim, server = _build(seed=3)
    sid = "S2"

    sim.inject_desired(sid, 7)
    # Update sent and outstanding, but unconfirmed: known-displayed is still None.
    assert len(_sends_for(sim, sid)) == 1
    assert _known_displayed(server, sid) is None
    assert _outstanding(server, sid) == 7
    assert sim.displayed(sid) is None

    # One step: deliver the update. The station now shows 7...
    sim.step()
    assert sim.displayed(sid) == 7
    # ...but the service has NOT received the ack, so it must not guess.
    assert _known_displayed(server, sid) is None
    assert _outstanding(server, sid) == 7

    # One step: deliver the acknowledgement. Only now does known-displayed advance.
    sim.step()
    assert _known_displayed(server, sid) == 7
    assert _outstanding(server, sid) is None
    assert sim.is_quiescent()


def test_genuinely_different_desired_is_not_suppressed_against_stale_value():
    """Suppression is tested only against the *current* confirmed known-displayed:
    a value that was displayed in the past no longer suppresses once the confirmed
    value has moved on."""
    sim, server = _build(seed=4)
    sid = "S3"

    sim.inject_desired(sid, 5)
    sim.run()
    assert _known_displayed(server, sid) == 5

    sim.inject_desired(sid, 9)
    sim.run()
    assert _known_displayed(server, sid) == 9
    base = len(_sends_for(sim, sid))

    # 5 was displayed earlier, but current known-displayed is 9: must NOT suppress.
    sim.inject_desired(sid, 5)
    sends = _sends_for(sim, sid)
    assert len(sends) == base + 1
    assert sends[-1].price == 5

    sim.run()
    assert _known_displayed(server, sid) == 5
    assert sim.displayed(sid) == 5


def test_coalesced_equal_desire_suppressed_only_after_confirming_ack():
    """When a second, equal desired arrives while an update is outstanding, the
    single-outstanding rule defers it; on the confirming ack the re-evaluation
    finds desired == known-displayed and suppresses it, yielding exactly one send
    and a convergent, quiescent state."""
    sim, server = _build(seed=5)
    sid = "S0"

    sim.inject_desired(sid, 4)            # send update(4); outstanding, unconfirmed
    assert len(_sends_for(sim, sid)) == 1
    assert _known_displayed(server, sid) is None

    sim.inject_desired(sid, 4)            # equal desire while outstanding: no new send
    assert len(_sends_for(sim, sid)) == 1

    sim.run()                             # deliver update, then ack -> re-evaluate
    assert len(_sends_for(sim, sid)) == 1  # ack re-eval suppresses (4 == 4)
    assert _known_displayed(server, sid) == 4
    assert _latest_desired(server, sid) == 4
    assert _outstanding(server, sid) is None
    assert sim.displayed(sid) == 4
