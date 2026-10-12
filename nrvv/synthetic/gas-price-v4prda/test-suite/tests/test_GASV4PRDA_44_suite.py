"""Tests for GASV4PRDA-44: acknowledgement handling when the desired price moved while in flight (GASV4PRDA-15)."""

import app
from nrvv_env import Simulation

A = 10
B = 20


def _quiet_simulation(seed):
    # No transport faults, no outages and no scripted central changes:
    # only the calls made by the test move the server.
    return Simulation(
        seed,
        app,
        stations=["S1"],
        prices=(A, B),
        change_rate=0,
        loss_rate=0,
        duplicate_rate=0,
        outages=False,
    )


def test_reverted_price_before_ack_sends_nothing_on_matching_ack():
    sim = _quiet_simulation(seed=7)
    server = sim._server

    server.desired_price_change("S1", A)
    assert len(sim.send_calls) == 1
    first = sim.send_calls[0]
    assert (first.station_id, first.price) == ("S1", A)
    n = first.sequence_number

    server.desired_price_change("S1", B)
    server.desired_price_change("S1", A)
    assert len(sim.send_calls) == 1  # the slot is full, so the changes wait

    server.acknowledgement_received("S1", n)
    assert len(sim.send_calls) == 1  # the station already shows A: nothing is sent

    for t in range(1, 121):
        server.advance_time(t)
    assert len(sim.send_calls) == 1  # no update remains outstanding to be resent

    # The slot is empty, so a real change is sent at once with the next sequence number.
    server.desired_price_change("S1", B)
    assert len(sim.send_calls) == 2
    fresh = sim.send_calls[1]
    assert (fresh.station_id, fresh.sequence_number, fresh.price) == ("S1", n + 1, B)


def test_changed_price_before_ack_sends_next_sequence_number_on_matching_ack():
    sim = _quiet_simulation(seed=7)
    server = sim._server

    server.desired_price_change("S1", A)
    n = sim.send_calls[0].sequence_number

    server.desired_price_change("S1", B)
    assert len(sim.send_calls) == 1

    server.acknowledgement_received("S1", n)
    assert len(sim.send_calls) == 2  # exactly one update after the acknowledgement
    fresh = sim.send_calls[1]
    assert (fresh.station_id, fresh.sequence_number, fresh.price) == ("S1", n + 1, B)

    # The new update is the outstanding one: a further change waits for its acknowledgement.
    server.desired_price_change("S1", A)
    assert len(sim.send_calls) == 2

    server.acknowledgement_received("S1", n + 1)
    assert len(sim.send_calls) == 3
    last = sim.send_calls[2]
    assert (last.station_id, last.sequence_number, last.price) == ("S1", n + 2, A)


def test_fresh_update_after_change_stays_outstanding_until_acked():
    sim = _quiet_simulation(seed=7)
    server = sim._server

    server.desired_price_change("S1", A)
    n = sim.send_calls[0].sequence_number

    server.desired_price_change("S1", B)
    server.acknowledgement_received("S1", n)
    fresh = sim.send_calls[-1]
    assert (fresh.sequence_number, fresh.price) == (n + 1, B)
    sent_so_far = len(sim.send_calls)

    # Without an acknowledgement, the fresh update is the one that gets resent.
    for t in range(1, 41):
        server.advance_time(t)
    later = sim.send_calls[sent_so_far:]
    assert later, "the fresh update was not resent without an acknowledgement"
    assert all((c.station_id, c.sequence_number, c.price) == ("S1", n + 1, B) for c in later)
