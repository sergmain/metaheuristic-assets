"""Tests for GASV4PRDA-2: a station is only ever sent the latest desired price."""

import app
from nrvv_env import Simulation

OLD = 10
NEW = 20
SEEDS = (1, 2, 3, 4, 5)


def _settle(sim, station_id, price, limit=2000):
    """Step until the station shows price, its acknowledgement arrived and nothing is in flight."""
    for _ in range(limit):
        sim.step()
        acked = any(call.station_id == station_id for call in sim.ack_calls)
        if sim.stations[station_id].display == price and acked and sim.in_flight() == 0:
            return
    raise AssertionError(f"{station_id} never settled on {price!r}")


def _supersede_before_sending(seed, **transport):
    """Give station S1 the price OLD, then NEW before any further sending; run to idle."""
    sim = Simulation(seed, app, stations=["S1"], change_rate=0.0, outages=False, **transport)
    app.desired_price_change("S1", OLD)
    _settle(sim, "S1", OLD)
    received_mark = len(sim.stations["S1"].received)
    sent_mark = len(sim.send_calls)
    app.desired_price_change("S1", NEW)
    sim.run_until_idle()
    delivered = [price for _, _, price in sim.stations["S1"].received[received_mark:]]
    sent = [call.price for call in sim.send_calls[sent_mark:]]
    return sim, delivered, sent


def test_superseded_price_is_never_delivered_on_clean_transport():
    for seed in SEEDS:
        sim, delivered, sent = _supersede_before_sending(seed, loss_rate=0.0, duplicate_rate=0.0)
        assert NEW in delivered, f"seed {seed}: latest price never delivered"
        assert OLD not in delivered, f"seed {seed}: superseded price delivered"
        assert OLD not in sent, f"seed {seed}: superseded price sent"
        assert sim.stations["S1"].display == NEW, f"seed {seed}: station not showing latest price"


def test_superseded_price_is_never_delivered_on_lossy_transport():
    for seed in SEEDS:
        sim, delivered, sent = _supersede_before_sending(seed, loss_rate=0.3, duplicate_rate=0.3)
        assert NEW in delivered, f"seed {seed}: latest price never delivered"
        assert OLD not in delivered, f"seed {seed}: superseded price delivered"
        assert OLD not in sent, f"seed {seed}: superseded price sent"
        assert sim.stations["S1"].display == NEW, f"seed {seed}: station not showing latest price"
