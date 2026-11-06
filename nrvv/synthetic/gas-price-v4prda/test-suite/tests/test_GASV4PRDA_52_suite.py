"""Tests for GASV4PRDA-52, the 30-second resend of the same outstanding update (GASV4PRDA-17)."""

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3)


def _simulation(seed):
    # No central changes and every update copy is lost, so the test's own
    # desired-price change is the only send and no acknowledgement arrives on its own.
    return Simulation(
        seed,
        server=app,
        stations=['S1'],
        change_rate=0.0,
        loss_rate=1.0,
        duplicate_rate=0.0,
        outages=False,
    )


def _advance_to(sim, t):
    while sim.now < t:
        sim.step()


def test_resend_at_30_and_60_seconds_then_silent_after_ack():
    for seed in SEEDS:
        sim = _simulation(seed)
        app.desired_price_change('S1', 100)
        assert len(sim.send_calls) == 1
        original = sim.send_calls[0]
        assert (original.time, original.station_id, original.price) == (0, 'S1', 100)
        seq = original.sequence_number

        _advance_to(sim, 29)
        assert len(sim.send_calls) == 1, f'seed {seed}: resend before 30 s'

        _advance_to(sim, 30)
        assert len(sim.send_calls) == 2, f'seed {seed}: no resend at 30 s'
        first = sim.send_calls[1]
        assert (first.time, first.station_id, first.sequence_number, first.price) == (30, 'S1', seq, 100)

        _advance_to(sim, 59)
        assert len(sim.send_calls) == 2, f'seed {seed}: second resend before 60 s'

        _advance_to(sim, 60)
        assert len(sim.send_calls) == 3, f'seed {seed}: no second resend at 60 s'
        second = sim.send_calls[2]
        assert (second.time, second.station_id, second.sequence_number, second.price) == (60, 'S1', seq, 100)

        app.acknowledgement_received('S1', seq)
        _advance_to(sim, 90)
        assert len(sim.send_calls) == 3, f'seed {seed}: resend after acknowledgement'


def test_no_resend_when_acknowledged_before_30_seconds():
    for seed in SEEDS:
        sim = _simulation(seed)
        app.desired_price_change('S1', 100)
        seq = sim.send_calls[0].sequence_number

        _advance_to(sim, 10)
        app.acknowledgement_received('S1', seq)
        _advance_to(sim, 200)
        assert len(sim.send_calls) == 1, f'seed {seed}: resend after early acknowledgement'


def test_ack_after_first_resend_stops_further_resends():
    for seed in SEEDS:
        sim = _simulation(seed)
        app.desired_price_change('S1', 100)
        seq = sim.send_calls[0].sequence_number

        _advance_to(sim, 30)
        assert len(sim.send_calls) == 2, f'seed {seed}: no resend at 30 s'
        app.acknowledgement_received('S1', seq)

        _advance_to(sim, 120)
        assert len(sim.send_calls) == 2, f'seed {seed}: resend after acknowledgement'
