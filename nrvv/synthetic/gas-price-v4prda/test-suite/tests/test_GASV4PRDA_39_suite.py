"""GASV4PRDA-39: each acknowledgement is matched to the update it confirms, in arrival order."""

from nrvv_env import Simulation

import app

STATION = "GASV4PRDA-39"
SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)


def _simulate(seed, **overrides):
    options = dict(
        stations=[STATION],
        change_rate=0.5,
        horizon=200,
        outages=False,
        loss_rate=0.0,
        duplicate_rate=0.0,
    )
    options.update(overrides)
    sim = Simulation(seed, app, **options)
    sim.run_until_idle()
    return sim


def _sends_of(sim, sequence_number):
    return [
        call
        for call in sim.send_calls
        if call.station_id == STATION and call.sequence_number == sequence_number
    ]


def _assert_acks_confirm_sent_updates(sim):
    """Every acknowledgement names an update sent earlier, and that update is never sent again after it."""
    first_ack_time = {}
    for ack in sim.ack_calls:
        assert ack.station_id == STATION
        sends = _sends_of(sim, ack.sequence_number)
        assert sends, f"acknowledgement {ack} confirms an update that was never sent"
        assert min(s.time for s in sends) <= ack.time
        assert all(s.time <= ack.time for s in sends), (
            f"update {ack.sequence_number} was sent again after its acknowledgement {ack}"
        )
        first_ack_time.setdefault(ack.sequence_number, ack.time)
    return first_ack_time


def test_each_ack_matches_the_update_it_confirms():
    total_acks = 0
    for seed in SEEDS:
        sim = _simulate(seed)
        _assert_acks_confirm_sent_updates(sim)
        total_acks += len(sim.ack_calls)
    assert total_acks > 0, "no acknowledgement arrived in any run"


def test_two_outstanding_updates_are_confirmed_by_their_own_acks_in_either_order():
    overlap_seen = False
    reversed_seen = False
    for seed in SEEDS:
        sim = _simulate(seed)
        first_ack = _assert_acks_confirm_sent_updates(sim)

        first_send = {}
        for call in sim.send_calls:
            if call.station_id == STATION:
                first_send.setdefault(call.sequence_number, call.time)
        sequences = sorted(first_send)

        # Two updates outstanding at once: an older update not yet confirmed when a newer one is sent.
        for call in sim.send_calls:
            if call.station_id != STATION:
                continue
            for older in sequences:
                if older >= call.sequence_number or first_send[older] >= call.time:
                    continue
                if older not in first_ack or first_ack[older] > call.time:
                    overlap_seen = True

        # Acknowledgements arriving with the newer update first (reversed arrival order).
        arrival = [ack.sequence_number for ack in sim.ack_calls]
        if any(later < earlier for earlier, later in zip(arrival, arrival[1:])):
            reversed_seen = True

        # Matching the right update lets the server converge on the latest desired price.
        assert sim.stations[STATION].display == sim.central.desired[STATION]

    assert overlap_seen, "no run had two outstanding updates for the station"
    assert reversed_seen, "no run delivered acknowledgements in reversed order"


def test_confirmed_updates_are_not_resent_under_loss_and_duplicates():
    total_acks = 0
    for seed in SEEDS:
        sim = _simulate(seed, change_rate=0.3, loss_rate=0.2, duplicate_rate=0.3)
        _assert_acks_confirm_sent_updates(sim)
        total_acks += len(sim.ack_calls)
    assert total_acks > 0, "no acknowledgement arrived in any run"
