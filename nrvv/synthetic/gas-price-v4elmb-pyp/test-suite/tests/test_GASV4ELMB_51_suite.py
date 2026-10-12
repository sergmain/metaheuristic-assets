"""GASV4ELMB-13: one update in flight per station keeps the last sent last delivered."""
import importlib

import app
from nrvv_env import Simulation

SEEDS = range(12)


def _fresh_simulation(seed, stations):
    importlib.reload(app)
    return Simulation(app, seed, stations=stations)


def _acknowledged_by(sim, station, seq, tick):
    return any(
        a.station == station and a.seq == seq and a.arrived is not None and a.arrived <= tick
        for a in sim.acks
    )


def _overlapping_unacknowledged_updates(sim):
    overlaps = []
    for index, send in enumerate(sim.sends):
        for earlier in sim.sends[:index]:
            if (earlier.station == send.station and earlier.seq != send.seq
                    and not _acknowledged_by(sim, earlier.station, earlier.seq, send.tick)):
                overlaps.append((earlier, send))
    return overlaps


def test_no_second_update_sent_while_first_is_unacknowledged():
    for seed in SEEDS:
        for stations in (1, 3):
            sim = _fresh_simulation(seed, stations)
            sim.run()
            assert sim.sends, (seed, stations)
            assert _overlapping_unacknowledged_updates(sim) == [], (seed, stations)


def test_newer_price_submitted_while_update_in_flight_is_exercised():
    while_in_flight = 0
    for seed in SEEDS:
        sim = _fresh_simulation(seed, 1)
        sim.run()
        while_in_flight += sum(1 for c in sim.changes if c.view_before['in_flight_seq'] is not None)
    assert while_in_flight > 0


def test_update_sent_after_ack_carries_desired_price_current_at_send():
    for seed in SEEDS:
        sim = _fresh_simulation(seed, 3)
        sim.run()
        for send in sim.sends:
            if not send.retransmission:
                assert send.price == send.desired, (seed, send.station, send.seq)


def test_last_delivered_price_equals_latest_desired_after_final_ack():
    for seed in SEEDS:
        for stations in (1, 3):
            sim = _fresh_simulation(seed, stations)
            sim.run()
            assert sim.final_display_mismatches() == [], (seed, stations)
