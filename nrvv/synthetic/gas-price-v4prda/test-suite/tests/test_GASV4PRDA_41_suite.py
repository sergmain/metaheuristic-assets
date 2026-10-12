"""GASV4PRDA-41: a newer desired price waits until the outstanding update is acknowledged (GASV4PRDA-4)."""

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)


def _run(seed, stations, change_rate, loss_rate, duplicate_rate, outages, horizon=120):
    sim = Simulation(
        seed,
        app,
        stations=stations,
        change_rate=change_rate,
        loss_rate=loss_rate,
        duplicate_rate=duplicate_rate,
        outages=outages,
        horizon=horizon,
    )
    sim.run_until_idle()
    return sim


def _outstanding(sim, station_id):
    """Yield (seq, price, sent_at, acked_at) per update of the station; acked_at is inf if never acknowledged."""
    first = {}
    for call in sim.send_calls:
        if call.station_id == station_id:
            first.setdefault(call.sequence_number, call)
    acked = {}
    for call in sim.ack_calls:
        if call.station_id == station_id:
            acked.setdefault(call.sequence_number, call.time)
    for seq, call in first.items():
        yield seq, call.price, call.time, acked.get(seq, float("inf"))


def _assert_held_until_ack(sim, station_id, seed):
    """No new update is sent while an earlier one is unacknowledged; return how many changes arrived during such a wait."""
    held = 0
    for seq, _, sent_at, acked_at in _outstanding(sim, station_id):
        newer_sends = [
            c
            for c in sim.send_calls
            if c.station_id == station_id and c.sequence_number != seq and sent_at <= c.time < acked_at
        ]
        assert not newer_sends, f"seed {seed}: update {newer_sends[0]} sent while seq {seq} was outstanding"
        held += sum(
            1
            for c in sim.central.changes
            if c.station_id == station_id and sent_at < c.time < acked_at
        )
    return held


def test_new_price_not_sent_before_outstanding_ack():
    held = 0
    for seed in SEEDS:
        sim = _run(seed, ["S1"], change_rate=1.0, loss_rate=0.0, duplicate_rate=0.0, outages=False)
        held += _assert_held_until_ack(sim, "S1", seed)
    # The scenario must really have produced new prices arriving during a wait.
    assert held > 0


def test_new_price_sent_after_outstanding_ack():
    released = 0
    for seed in SEEDS:
        sim = _run(seed, ["S1"], change_rate=1.0, loss_rate=0.0, duplicate_rate=0.0, outages=False)
        for seq, price, _, acked_at in _outstanding(sim, "S1"):
            latest = sim.central.desired_at("S1", acked_at)
            if latest == price:
                continue  # nothing newer than the outstanding price
            released += 1
            fresh = [
                c
                for c in sim.send_calls
                if c.station_id == "S1" and c.sequence_number != seq and c.time >= acked_at
            ]
            assert fresh, f"seed {seed}: nothing sent after ack of seq {seq}, desired {latest}"
            first = fresh[0]
            assert first.price == sim.central.desired_at("S1", first.time), (
                f"seed {seed}: first update after ack carries {first.price}"
            )
    assert released > 0


def test_newer_price_held_under_loss_duplicates_and_outages():
    held = 0
    for seed in SEEDS:
        sim = _run(seed, ["S1"], change_rate=1.0, loss_rate=0.3, duplicate_rate=0.3, outages=True, horizon=200)
        held += _assert_held_until_ack(sim, "S1", seed)
    assert held > 0


def test_hold_applies_per_station():
    held = 0
    for seed in SEEDS:
        sim = _run(
            seed,
            ["S1", "S2", "S3"],
            change_rate=0.5,
            loss_rate=0.1,
            duplicate_rate=0.1,
            outages=False,
        )
        for station_id in ("S1", "S2", "S3"):
            held += _assert_held_until_ack(sim, station_id, seed)
    assert held > 0
