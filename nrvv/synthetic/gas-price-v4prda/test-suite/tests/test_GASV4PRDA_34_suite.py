"""GASV4PRDA-34: a fresh send of a station's most recently sent price is suppressed; a different price is sent."""
import importlib

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)


def _run(seed, **options):
    importlib.reload(app)  # fresh module state for every simulation
    sim = Simulation(seed=seed, server=app, **options)
    sim.run_until_idle()
    return sim


def _last_send_before(sim, station_id, t):
    earlier = [c for c in sim.send_calls if c.station_id == station_id and c.time < t]
    return earlier[-1] if earlier else None


def _sends_at(sim, station_id, t):
    return [c for c in sim.send_calls if c.station_id == station_id and c.time == t]


def _acked_before(sim, station_id, sequence_number, t):
    return any(
        a.station_id == station_id and a.sequence_number == sequence_number and a.time < t
        for a in sim.ack_calls
    )


def _check_suppression(sim):
    """Every change to the most recently sent price must send nothing new; returns how many were checked."""
    checked = 0
    for change in sim.central.changes:
        last = _last_send_before(sim, change.station_id, change.time)
        if last is None or last.price != change.price:
            continue
        checked += 1
        for call in _sends_at(sim, change.station_id, change.time):
            # a resend of the outstanding update reuses its sequence number and is allowed
            fresh = call.sequence_number != last.sequence_number
            assert not (fresh and call.price == change.price), (
                f'{change.station_id} at t={change.time}: price {change.price} was sent again as sequence {call.sequence_number}'
            )
    return checked


def _check_proceed(sim):
    """A different price with an empty slot must be sent at once; returns how many were checked."""
    checked = 0
    for change in sim.central.changes:
        last = _last_send_before(sim, change.station_id, change.time)
        if last is None or last.price == change.price:
            continue
        if not _acked_before(sim, change.station_id, last.sequence_number, change.time):
            continue  # slot still full: the send waits for the acknowledgement
        checked += 1
        sent = [c.price for c in _sends_at(sim, change.station_id, change.time)]
        assert change.price in sent, (
            f'{change.station_id} at t={change.time}: price {change.price} differs from last sent {last.price} with empty slot but was not sent'
        )
    return checked


def test_same_price_as_last_sent_is_suppressed():
    checked = 0
    for seed in SEEDS:
        checked += _check_suppression(_run(seed))
    assert checked > 0


def test_different_price_with_empty_slot_is_sent():
    checked = 0
    for seed in SEEDS:
        checked += _check_proceed(_run(seed))
    assert checked > 0


def test_alternating_prices_are_suppressed_and_sent():
    checked = 0
    for seed in SEEDS:
        sim = _run(seed, prices=(10, 20), change_rate=1.0, horizon=60)
        checked += _check_suppression(sim)
        checked += _check_proceed(sim)
    assert checked > 0


def test_final_display_matches_last_desired_price():
    for seed in SEEDS:
        sim = _run(seed, loss_rate=0.0, duplicate_rate=0.0, outages=False)
        for sid, station in sim.stations.items():
            desired = sim.central.desired[sid]
            assert station.display == desired, f'seed {seed}, station {sid}: display {station.display}, desired {desired}'
            sent = [c for c in sim.send_calls if c.station_id == sid]
            if sent:
                assert sent[-1].price == desired, f'seed {seed}, station {sid}: last sent {sent[-1].price}, desired {desired}'
