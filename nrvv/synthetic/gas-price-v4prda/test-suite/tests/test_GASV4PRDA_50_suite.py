"""GASV4PRDA-5 (test case GASV4PRDA-50): once the outstanding update is acknowledged, the station
gets an update carrying the current desired price, not the price of the acknowledged update."""

import app
from nrvv_env import Simulation

SEEDS = range(40)


def _acknowledged_while_changed(sim):
    """Yield (station_id, ack_time, desired) for each acknowledgement that meets the precondition.

    The acknowledged update is the latest one sent to its station before the acknowledgement,
    its carried price differs from the desired price at that time, and the central service issues
    no further desired price change for the station at or after the acknowledgement.
    """
    for ack in sim.ack_calls:
        sid = ack.station_id
        earlier = [c for c in sim.send_calls if c.station_id == sid and c.time < ack.time]
        if not earlier or earlier[-1].sequence_number != ack.sequence_number:
            continue
        if any(c.station_id == sid and c.time >= ack.time for c in sim.central.changes):
            continue
        desired = sim.central.desired_at(sid, ack.time)
        if desired == earlier[-1].price:
            continue
        yield sid, ack.time, desired


def _check_update_after_ack(sim):
    """Check every precondition case of the run; return how many were checked."""
    checked = 0
    for sid, ack_time, desired in _acknowledged_while_changed(sim):
        sent = [c for c in sim.send_calls if c.station_id == sid and c.time >= ack_time]
        assert sent, f"{sid}: no update sent after the acknowledgement at t={ack_time}"
        assert sent[-1].price == desired, (
            f"{sid}: update sent after the acknowledgement at t={ack_time} carries "
            f"{sent[-1].price!r}, current desired price is {desired!r}"
        )
        checked += 1
    return checked


def test_update_after_ack_carries_current_desired_price_on_reliable_transport():
    checked = 0
    for seed in SEEDS:
        sim = Simulation(
            seed,
            app,
            stations=3,
            horizon=60,
            change_rate=0.3,
            loss_rate=0.0,
            duplicate_rate=0.0,
            outages=False,
        )
        sim.run_until_idle()
        checked += _check_update_after_ack(sim)
    assert checked > 0, "no run reached the precondition, so nothing was checked"


def test_update_after_ack_carries_current_desired_price_with_loss_duplicates_and_outages():
    checked = 0
    for seed in SEEDS:
        sim = Simulation(seed, app, stations=3, horizon=150)
        sim.run_until_idle()
        checked += _check_update_after_ack(sim)
    assert checked > 0, "no run reached the precondition, so nothing was checked"
