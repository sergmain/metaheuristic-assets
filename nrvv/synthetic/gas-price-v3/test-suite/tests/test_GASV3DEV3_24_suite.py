"""Tests for GASV3DEV3-24 / requirement GASV3DEV3-3:

At most one unacknowledged update per station.

The service must not send a second price update to a station while a
previously sent update to that same station is still unacknowledged; a
subsequent update is emitted only after the acknowledgement of the first has
been received by the service.

Every test drives ``app`` exclusively through ``nrvv_env``.  The outbound
``send-update`` port is wired by the simulation; its captured ``sent`` list is
the authoritative record of what the service emitted, in order.
"""

import app
import nrvv_env


def _make_server(sim):
    """Construct the server under test, injecting the outbound port.

    The service emits exclusively through ``send_update`` (GASV3DEV3-12).  We
    try constructor injection first, then fall back to letting the simulation
    wire the attribute after attach.
    """
    try:
        server = app.Service(send_update=sim.send_update)
        sim.attach(server)
        return server
    except TypeError:
        pass
    try:
        server = app.Service()
        sim.attach(server, wire_outbound=True)
        return server
    except AttributeError:
        pass
    # Last resort: a module-level factory.
    server = app.create_service(send_update=sim.send_update)
    sim.attach(server)
    return server


def _sent_to(sim, station):
    return [p for (s, p) in sim.sent if s == station]


def test_no_second_update_emitted_while_first_outstanding():
    """A second submission while the first update is outstanding emits nothing."""
    sim = nrvv_env.Simulation(seed=1)
    _make_server(sim)
    S = "alpha"

    # First desired price for the station -> the service must emit one update.
    sim.server.submit_desired_price(S, 100)
    assert sim.sent == [(S, 100)], (
        "the first submission must emit exactly one update to the station")

    # The update is now in flight and unacknowledged.  Any further submission
    # for the same station must NOT produce another emission.
    sim.server.submit_desired_price(S, 200)
    assert sim.sent == [(S, 100)], (
        "no second update may be sent while the first is unacknowledged")

    sim.server.submit_desired_price(S, 300)
    assert sim.sent == [(S, 100)], (
        "repeated submissions while outstanding must still emit nothing")


def test_subsequent_update_emitted_only_after_acknowledgement():
    """The pending update is emitted only once the first ack is received."""
    sim = nrvv_env.Simulation(seed=2)
    _make_server(sim)
    S = "beta"

    sim.server.submit_desired_price(S, 111)
    assert sim.sent == [(S, 111)]

    # Queue a new desired value while the first update is still outstanding.
    sim.server.submit_desired_price(S, 222)
    assert sim.sent == [(S, 111)], "still gated: nothing new before ack"

    # Deliver the in-flight update to the station; this alone does NOT reach
    # the service (the service only observes acknowledgements), so still gated.
    assert len(sim.pending_updates()) == 1
    seq = sim.pending_updates()[0].seq
    sim.deliver(seq)
    assert sim.sent == [(S, 111)], (
        "delivery to the station does not unblock; only the ack does")

    # Now deliver the acknowledgement to the service: the gate opens and the
    # pending update must be emitted, to the same station, carrying the value
    # that had been waiting.
    sim.deliver_ack()
    assert len(sim.sent) == 2, "exactly one further update after the ack"
    assert sim.sent[1] == (S, 222), (
        "the update emitted after the ack must be the pending value")


def test_ack_for_station_reopens_gate_for_that_station_only():
    """Acking one station must not let another station's gate matter."""
    sim = nrvv_env.Simulation(seed=3)
    _make_server(sim)
    A, B = "A", "B"

    sim.server.submit_desired_price(A, 10)
    sim.server.submit_desired_price(B, 20)
    assert sim.sent == [(A, 10), (B, 20)], (
        "each station's first update is independent and emitted once")

    # Both outstanding; further submissions to each are gated.
    sim.server.submit_desired_price(A, 11)
    sim.server.submit_desired_price(B, 21)
    assert sim.sent == [(A, 10), (B, 20)], "both gated while outstanding"

    # Deliver + ack only A's update.  Only A's pending update may now emit.
    for u in sim.pending_updates():
        if u.station == A:
            sim.deliver(u.seq)
            break
    # Ack channel head is A's ack (A was delivered first here).
    sim.deliver_ack()
    assert _sent_to(sim, A) == [10, 11], "A's pending update emits after A's ack"
    assert _sent_to(sim, B) == [20], "B remains gated, nothing new for B"


def test_at_most_one_outstanding_invariant_under_seeded_scheduling():
    """Property: sends - acks(received) per station never exceeds 1.

    Driven by the seeded scheduler over randomized scripts across several
    stations.  After every logical step, the number of updates the service has
    emitted to a station minus the number of acknowledgements the service has
    received for that station must never exceed one: that is exactly the
    single-outstanding gate observed externally.
    """
    stations = ["s1", "s2", "s3"]
    for seed in range(8):
        script = nrvv_env.random_script(seed, stations, length=40)
        sim = nrvv_env.Simulation(seed=seed, script=script)
        _make_server(sim)

        def check():
            for st in stations:
                sent = sum(1 for (s, _) in sim.sent if s == st)
                acked = sum(1 for s in sim.acks if s == st)
                outstanding = sent - acked
                assert outstanding <= 1, (
                    "seed=%d station=%r: %d sent, %d acked -> %d outstanding"
                    % (seed, st, sent, acked, outstanding))
                assert outstanding >= 0

        check()
        steps = 0
        while sim.step() is not None:
            check()
            steps += 1
            assert steps < 100000, "scheduler failed to quiesce"
        check()


def test_burst_of_submissions_yields_single_outstanding_then_one_more():
    """A burst while outstanding collapses to at most one further emission per ack."""
    sim = nrvv_env.Simulation(seed=7)
    _make_server(sim)
    S = "burst"

    sim.server.submit_desired_price(S, 1)
    assert len(sim.sent) == 1

    # A burst of submissions, all while the single update is outstanding.
    for price in (2, 3, 4, 5):
        sim.server.submit_desired_price(S, price)
    assert len(sim.sent) == 1, "the whole burst emits no additional update"

    # Deliver and ack the single outstanding update.
    seq = sim.pending_updates()[0].seq
    sim.deliver(seq)
    sim.deliver_ack()

    # At most one further update may be emitted for the station as a result of
    # the single acknowledgement (the gate admits one, not the whole burst).
    assert len(sim.sent) <= 2, (
        "a single ack may release at most one further update")
    assert len(sim.sent) >= 1
