"""Verification of GASV4PRDA-19 (full-price updates; station display relies on last received update).

Driven only through nrvv_env: the server is the module ``app``; the central
service, the stations and the transport are simulated by ``Simulation``.
"""

from collections import Counter

import app
from nrvv_env import MAX_DELAY, Simulation

SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)
PRICES = (10, 20, 30, 40, 50)
RESEND_PERIOD = 30


def _run(seed, **options):
    sim = Simulation(seed=seed, server=app, **options)
    sim.run_until_idle()
    return sim


def _last_received_at(station, t):
    """Price of the last copy the station received at or before logical time t."""
    price = None
    for when, _, value in station.received:
        if when > t:
            break
        price = value
    return price


def test_station_displays_only_price_of_last_update_received():
    for seed in SEEDS:
        sim = _run(seed, loss_rate=0.2, duplicate_rate=0.3)
        for station in sim.stations.values():
            for when, _, _ in station.received:
                assert station.display_at(when) == _last_received_at(station, when), (
                    seed, station.station_id, when)
            if station.received:
                assert station.display == station.received[-1][2], (seed, station.station_id)


def test_station_acknowledges_every_update_copy_it_receives():
    for seed in SEEDS:
        sim = _run(seed, loss_rate=0.0, duplicate_rate=0.3)
        received = Counter(
            (when, sid, seq)
            for sid, station in sim.stations.items()
            for when, seq, _ in station.received
        )
        acks_sent = Counter(
            (m.sent_at, m.station_id, m.sequence_number)
            for m in sim.messages
            if m.kind == "ack"
        )
        assert acks_sent == received, seed
        assert len(sim.ack_calls) == sum(received.values()), seed


def test_update_carries_complete_price_and_no_other_field():
    for seed in SEEDS:
        sim = _run(seed, loss_rate=0.1, duplicate_rate=0.2)
        assert sim.send_calls, seed
        for call in sim.send_calls:
            assert type(call.price) is int and call.price in PRICES, (seed, call)
        for msg in sim.messages:
            if msg.kind == "update":
                assert msg.price in PRICES, (seed, msg.price)
        for station in sim.stations.values():
            for _, _, price in station.received:
                assert price in PRICES, (seed, price)


def test_final_display_equals_latest_desired_price_without_faults():
    for seed in SEEDS:
        sim = _run(seed, change_rate=0.2, loss_rate=0.0, duplicate_rate=0.0, outages=False)
        assert sim.central.changes, seed
        for sid, station in sim.stations.items():
            assert station.display == sim.central.desired[sid], (seed, sid)


def test_delayed_stale_copy_does_not_leave_stale_price_last():
    checked = 0
    delayed_copies = 0
    for seed in SEEDS:
        sim = _run(
            seed,
            change_rate=0.02,
            horizon=600,
            loss_rate=0.0,
            duplicate_rate=1.0,
            outages=False,
        )
        delayed_copies += sum(
            1
            for m in sim.messages
            if m.kind == "update" and m.delivered_at is not None and m.delivered_at > m.sent_at
        )
        for sid, station in sim.stations.items():
            sends = [c for c in sim.send_calls if c.station_id == sid]
            if not sends:
                continue
            newest = sends[-1]
            if len(sends) > 1 and newest.time - sends[-2].time < RESEND_PERIOD:
                continue
            checked += 1
            assert station.display == newest.price, (seed, sid)
            assert _last_received_at(station, sim.now) == newest.price, (seed, sid)
    assert checked > 0
    assert delayed_copies > 0
