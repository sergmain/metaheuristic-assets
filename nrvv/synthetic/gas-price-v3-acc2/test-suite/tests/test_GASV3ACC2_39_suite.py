"""Suite for GASV3ACC2-39 (requirement GASV3ACC2-14): send at the earliest
permissible moment.

A send is permissible for a station exactly when it has no outstanding update
and its latest desired price differs from its last acknowledged value. On a
desired-price submission the server must emit immediately if the station is idle
and diverged; on an acknowledgement that clears the outstanding update it must
emit immediately if still diverged. In the complementary cases -- an already
outstanding station on submit, or a station whose desired equals its last
acknowledged value -- no send is issued. No batching window or artificial delay
exists.

Every test drives `app` only through `nrvv_env`: it submits/acknowledges/delivers
by stepping the simulation, and observes emissions through the simulation's
public `sent` log. The environment performs exactly one atomic action per
step() with no clock, so a send appearing in the same step as a submit or ack
proves immediacy (no intervening delay or batching interval).
"""

import app
import nrvv_env


# Marker for "never acknowledged": the requirement's sentinel last-acknowledged
# value, distinct from every real price, so a first desired is always diverged.
_SENTINEL = object()


def _connect(sim):
    """Wire app's outbound transmit port to the simulation and bind the server.

    The simulation's connect(factory) builds the server as factory(transmit) and
    binds it; thereafter the simulation drives app through its inbound
    operations and captures emissions on transmit.
    """
    last_err = None
    if hasattr(app, "Server"):
        try:
            return sim.connect(app.Server)
        except Exception as e:  # pragma: no cover - wiring fallback only
            last_err = e
    for name in ("create_server", "make_server", "build_server",
                 "new_server", "server", "create", "App"):
        factory = getattr(app, name, None)
        if callable(factory):
            try:
                return sim.connect(factory)
            except Exception as e:  # pragma: no cover - wiring fallback only
                last_err = e
    raise AssertionError(
        "could not wire app to the nrvv_env transmit port: %r" % (last_err,))


def _drive_and_check(sim, counters):
    """Step the simulation to quiescence, asserting on every step that a send is
    issued exactly when (and only when) it is permissible, and that each emitted
    send carries the right (station, price). Updates ``counters`` with how many
    times each situation was exercised.
    """
    desired = {}      # station -> latest desired price seen by the server
    last_ack = {}     # station -> last acknowledged price (default sentinel)

    while True:
        sent_before = len(sim.sent)
        # Which stations have an outstanding (emitted, not-yet-acked) update,
        # observed just before the step: the simulation holds such updates
        # in-flight from emission until acknowledgement.
        outstanding_before = set(u.station for u in sim.in_flight)

        action = sim.step()
        if action is None:
            break
        new_sends = sim.sent[sent_before:]
        kind = action[0]

        if kind == "submit":
            s, p = action[1], action[2]
            was_outstanding = s in outstanding_before
            la = last_ack.get(s, _SENTINEL)
            diverged = (la is _SENTINEL) or (la != p)
            desired[s] = p
            if (not was_outstanding) and diverged:
                assert new_sends == [(s, p)], (
                    "idle+diverged submit must send exactly (%r, %r) with no "
                    "delay or batching; got %r" % (s, p, new_sends))
                counters["submit_send"] += 1
            else:
                assert new_sends == [], (
                    "submit must not send while outstanding or when converged; "
                    "got %r" % (new_sends,))
                if was_outstanding:
                    counters["submit_suppress_outstanding"] += 1
                else:
                    counters["submit_suppress_converged"] += 1

        elif kind == "ack":
            u = action[1]
            s, acked = u.station, u.price
            last_ack[s] = acked
            d = desired.get(s, _SENTINEL)
            still_diverged = (d is not _SENTINEL) and (d != acked)
            if still_diverged:
                assert new_sends == [(s, d)], (
                    "ack clearing the outstanding update while still diverged "
                    "must send latest desired (%r, %r) immediately; got %r"
                    % (s, d, new_sends))
                counters["ack_send"] += 1
            else:
                assert new_sends == [], (
                    "ack must not send once the station is converged; got %r"
                    % (new_sends,))
                counters["ack_suppress"] += 1

        elif kind == "deliver":
            assert new_sends == [], (
                "delivery involves no server operation and must issue no send; "
                "got %r" % (new_sends,))
            counters["deliver"] += 1

        else:  # pragma: no cover - defensive
            raise AssertionError("unexpected action: %r" % (action,))


def _new_counters():
    return {
        "submit_send": 0,
        "submit_suppress_outstanding": 0,
        "submit_suppress_converged": 0,
        "ack_send": 0,
        "ack_suppress": 0,
        "deliver": 0,
    }


def test_first_submit_sends_immediately_no_delay():
    """An idle, diverged station (its first desired differs from the sentinel)
    emits a send within the very submit step, with nothing else intervening."""
    sim = nrvv_env.Simulation([("S0", 42)])
    _connect(sim)

    assert sim.sent == []            # nothing sent before any submit
    action = sim.step()              # the only available action is the submit
    assert action[0] == "submit"
    # The send was issued synchronously during submit_desired_price: no
    # delivery, acknowledgement, or batching window was needed.
    assert sim.sent == [("S0", 42)]


def test_ack_sends_immediately_when_still_diverged():
    """When the desired price changes while an update is outstanding, the ack
    that clears it must immediately emit the new latest desired value, and only
    that value."""
    # Two desired prices for one station; whatever transport order the seed
    # picks, the invariant checker verifies the ack-triggered send is immediate
    # and carries the latest desired price.
    counters = _new_counters()
    for seed in (0, 1, 2, 3, 4, 5):
        sim = nrvv_env.Simulation([("S0", 10), ("S0", 20)], seed=seed)
        _connect(sim)
        _drive_and_check(sim, counters)
    # Across these runs the "submit while outstanding then ack still diverged"
    # path is exercised, producing an ack-triggered immediate send.
    assert counters["ack_send"] > 0
    assert counters["submit_suppress_outstanding"] > 0


def test_converged_station_issues_no_further_send():
    """A single desired price runs submit -> deliver -> ack deterministically;
    the ack finds the station converged (desired == acknowledged) and must not
    issue any further send, leaving exactly one emission for the whole run."""
    sim = nrvv_env.Simulation([("S0", 7)])
    _connect(sim)
    sim.run()
    # Exactly one send ever: the initial idle+diverged emission. The ack that
    # advanced last-acknowledged to 7 found desired == 7 and suppressed.
    assert sim.sent == [("S0", 7)]
    assert sim.quiescent()


def test_sends_occur_exactly_at_permissible_moments_random():
    """Across several seeded, out-of-order runs, a send is issued on precisely
    the permissible steps (idle+diverged submit, or ack still diverged) and on
    no others (never on delivery, never while outstanding). The per-step checks
    also confirm immediacy: each permissible send lands in its own step."""
    counters = _new_counters()
    for seed in (1, 2, 3, 7, 13, 101):
        sim = nrvv_env.Simulation.from_seed(
            seed, num_stations=3, num_events=30, price_min=1, price_max=4)
        _connect(sim)
        _drive_and_check(sim, counters)
        assert sim.quiescent()

    # The run was non-vacuous: every headline situation of the criterion was
    # actually exercised while the invariant held.
    assert counters["submit_send"] > 0, "idle+diverged submits must occur"
    assert counters["submit_suppress_outstanding"] > 0, \
        "submits while outstanding must occur and be suppressed"
    assert counters["ack_send"] > 0, "ack-triggered diverged sends must occur"
    assert counters["deliver"] > 0, "deliveries must occur without sending"


def test_resubmitting_acknowledged_value_is_suppressed():
    """Re-submitting the value a station has already acknowledged leaves it
    converged, so no send is issued on that submit (nor on the ack that first
    reached convergence)."""
    counters = _new_counters()
    # One station, the same price repeated: once acknowledged, later submits of
    # the same value find desired == last-acknowledged and must not send.
    for seed in range(10):
        sim = nrvv_env.Simulation([("S0", 7)] * 10, seed=seed)
        _connect(sim)
        _drive_and_check(sim, counters)
        assert sim.quiescent()

    # Convergence via acknowledgement always occurs here; a submit landing on an
    # already-converged idle station is exercised across these seeds.
    assert counters["ack_suppress"] > 0, \
        "acks that reach convergence must suppress"
    assert counters["submit_suppress_converged"] > 0, \
        "submits of an already-acknowledged value must be suppressed"
    # And of course the very first emission did go out.
    assert counters["submit_send"] > 0
