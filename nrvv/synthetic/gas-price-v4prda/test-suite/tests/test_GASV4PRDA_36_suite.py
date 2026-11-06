"""GASV4PRDA-36: convergence within the 60 s budget after a lost update (GASV4PRDA-18)."""

import importlib

import app
from nrvv_env import Simulation

SEEDS = range(1, 41)
RUN_SECONDS = 400
LOSS_RATE = 0.3


def _run(seed):
    importlib.reload(app)
    sim = Simulation(
        seed,
        server=app,
        stations=1,
        loss_rate=LOSS_RATE,
        duplicate_rate=0.0,
        outages=False,
    )
    sim.run(RUN_SECONDS)
    return sim


def _update_message(sim, call):
    for msg in sim.messages:
        if (
            msg.kind == 'update'
            and not msg.duplicate
            and msg.station_id == call.station_id
            and msg.sequence_number == call.sequence_number
            and msg.sent_at == call.time
        ):
            return msg
    return None


def _ack_message(sim, update):
    for msg in sim.messages:
        if (
            msg.kind == 'ack'
            and msg.station_id == update.station_id
            and msg.sequence_number == update.sequence_number
            and msg.sent_at == update.delivered_at
        ):
            return msg
    return None


def _scenarios_of(sim):
    """Find each update lost in transit that a desired-price change overtook while outstanding."""
    found = []
    for lost in sim.send_calls:
        lost_msg = _update_message(sim, lost)
        if lost_msg is None or lost_msg.status != 'lost':
            continue
        resend = next(
            (
                c for c in sim.send_calls
                if c.station_id == lost.station_id
                and c.sequence_number == lost.sequence_number
                and c.time > lost.time
            ),
            None,
        )
        if resend is None:
            continue
        station_changes = [ch for ch in sim.central.changes if ch.station_id == lost.station_id]
        during = [ch for ch in station_changes if lost.time < ch.time <= resend.time]
        if not during:
            continue
        t0 = during[0].time
        if any(t0 < ch.time <= t0 + 45 for ch in station_changes):
            continue
        resend_msg = _update_message(sim, resend)
        if resend_msg is None or resend_msg.status != 'delivered':
            continue
        ack = _ack_message(sim, resend_msg)
        if ack is None or ack.status != 'delivered':
            continue
        fresh = next(
            (
                c for c in sim.send_calls
                if c.station_id == lost.station_id
                and c.sequence_number != lost.sequence_number
                and c.time >= ack.delivered_at
            ),
            None,
        )
        if fresh is None:
            continue
        fresh_msg = _update_message(sim, fresh)
        if fresh_msg is None or fresh_msg.status != 'delivered':
            continue
        fresh_ack = _ack_message(sim, fresh_msg)
        fresh_ack_ok = fresh_ack is not None and fresh_ack.status == 'delivered'
        found.append({
            't0': t0,
            'resend_time': resend.time,
            'resend_delivered': resend_msg.delivered_at,
            'resend_ack_sent': ack.sent_at,
            'resend_ack_received': ack.delivered_at,
            'fresh_time': fresh.time,
            'fresh_delivered': fresh_msg.delivered_at,
            'fresh_ack_sent': fresh_ack.sent_at if fresh_ack_ok else None,
            'fresh_ack_received': fresh_ack.delivered_at if fresh_ack_ok else None,
        })
    return found


def _scenarios():
    found = []
    for seed in SEEDS:
        found.extend(_scenarios_of(_run(seed)))
    assert found, 'no seed produced a lost update overtaken by a desired-price change'
    return found


def test_resend_is_sent_by_t0_plus_30():
    for sc in _scenarios():
        assert sc['resend_time'] <= sc['t0'] + 30, sc


def test_fresh_update_is_sent_by_t0_plus_40():
    for sc in _scenarios():
        assert sc['fresh_time'] <= sc['t0'] + 40, sc


def test_fresh_update_is_delivered_by_t0_plus_45():
    for sc in _scenarios():
        assert sc['fresh_delivered'] <= sc['t0'] + 45, sc


def test_resend_and_fresh_deliveries_take_at_most_5_seconds():
    for sc in _scenarios():
        assert sc['resend_delivered'] - sc['resend_time'] <= 5, sc
        assert sc['fresh_delivered'] - sc['fresh_time'] <= 5, sc


def test_acknowledgements_return_within_5_seconds():
    for sc in _scenarios():
        assert sc['resend_ack_received'] - sc['resend_ack_sent'] <= 5, sc
        if sc['fresh_ack_received'] is not None:
            assert sc['fresh_ack_received'] - sc['fresh_ack_sent'] <= 5, sc
