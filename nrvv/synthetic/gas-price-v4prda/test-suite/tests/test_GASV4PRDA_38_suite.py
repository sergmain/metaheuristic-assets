"""Tests for GASV4PRDA-38: an unchanged price is not resent to a station (GASV4PRDA-6)."""

import app
from nrvv_env import Simulation


def _sim(station_id, seed):
    return Simulation(
        seed,
        server=app,
        stations=[station_id],
        horizon=0,
        loss_rate=0.0,
        duplicate_rate=0.0,
        outages=False,
    )


def _sends_to(sim, station_id):
    return [call for call in sim.send_calls if call.station_id == station_id]


def test_same_price_again_sends_no_update_to_station():
    for seed in (1, 2, 3):
        station = f"S-same-{seed}"
        sim = _sim(station, seed)
        app.desired_price_change(station, "1.50")
        sim.run(1)
        sent_before = _sends_to(sim, station)
        assert [c.price for c in sent_before] == ["1.50"]
        app.desired_price_change(station, "1.50")
        sim.run(40)
        assert _sends_to(sim, station) == sent_before


def test_same_price_again_after_ack_sends_no_update_to_station():
    for seed in (4, 5, 6):
        station = f"S-acked-{seed}"
        sim = _sim(station, seed)
        app.desired_price_change(station, "1.50")
        sim.run_until_idle()
        assert len(sim.ack_calls) == 1
        sent_before = _sends_to(sim, station)
        assert [c.price for c in sent_before] == ["1.50"]
        app.desired_price_change(station, "1.50")
        sim.run(40)
        assert _sends_to(sim, station) == sent_before


def test_return_to_sent_price_while_update_pending_sends_nothing_more():
    for seed in (7, 8, 9):
        station = f"S-revert-{seed}"
        sim = _sim(station, seed)
        app.desired_price_change(station, "1.50")
        app.desired_price_change(station, "2.00")
        app.desired_price_change(station, "1.50")
        sim.run(40)
        assert [c.price for c in _sends_to(sim, station)] == ["1.50"]
