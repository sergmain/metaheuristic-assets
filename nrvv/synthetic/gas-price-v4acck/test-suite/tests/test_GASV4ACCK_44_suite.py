import pytest

import app
from nrvv_env import Simulation

DEADLINE = 300  # logical seconds, 5 minutes
SEEDS = [1, 2, 3, 4, 5, 6]
STATIONS = ['S1', 'S2', 'S3']


def _make_server():
    candidates = [
        obj for obj in vars(app).values()
        if isinstance(obj, type)
        and all(callable(getattr(obj, m, None))
                for m in ('set_latest_price', 'tick', 'acknowledgement_received'))
    ]
    if not candidates:
        pytest.fail('app has no server class with set_latest_price, tick and acknowledgement_received')
    return candidates[0]()


def _run(seed, **kwargs):
    sim = Simulation(seed, STATIONS, **kwargs)
    sim.bind(_make_server())
    sim.run_to_end()
    return sim


def _carried_by_unacknowledged(sim, change):
    # an update with the same price was sent before the change and is not yet acknowledged at the change time
    return any(
        r.station == change.station and r.price == change.price
        and r.sent_at <= change.time
        and (r.acknowledged_at is None or r.acknowledged_at >= change.time)
        for r in sim.sends
    )


def _dispatched_in_window(sim, change):
    return any(
        r.station == change.station and change.time <= r.sent_at <= change.time + DEADLINE
        for r in sim.sends
    )


def test_new_price_dispatched_within_five_minutes():
    checked = 0
    for seed in SEEDS:
        sim = _run(seed)
        for change in sim.changes:
            if _carried_by_unacknowledged(sim, change):
                continue
            checked += 1
            assert _dispatched_in_window(sim, change), (seed, change)
    assert checked > 0


def test_repeated_price_dispatched_within_five_minutes_unless_carried():
    checked = 0
    for seed in SEEDS:
        sim = _run(seed, changes_per_station=(3, 6), price_range=(1, 2))
        for change in sim.changes:
            if _carried_by_unacknowledged(sim, change):
                continue
            checked += 1
            assert _dispatched_in_window(sim, change), (seed, change)
    assert checked > 0


def test_change_to_outstanding_price_is_not_counted_stale():
    exempt = 0
    for seed in SEEDS:
        sim = _run(seed, changes_per_station=(3, 6), price_range=(1, 1))
        for change in sim.changes:
            if _carried_by_unacknowledged(sim, change):
                exempt += 1
        # every station still converges on the final desired price
        assert sim.held_prices() == sim.reference_final_prices, seed
    assert exempt > 0


def test_stations_end_on_final_latest_price():
    for seed in SEEDS:
        sim = _run(seed, changes_per_station=(2, 4))
        assert sim.held_prices() == sim.reference_final_prices, seed
