'''GASV4ACCJ-36: a desired price change made while a send is outstanding gets the station's next send by t+60 s.'''

import importlib

import app
from nrvv_env import Simulation

BOUND = 60.0
OUTSTANDING_WINDOW = 30.0
SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)


def _snapshot(sim):
    snap = {}
    for station in sim.stations:
        unacked = [r.sent_at for r in sim.sends() if r.station == station and r.ack_arrived_at is None]
        acked = [r.price for r in sim.acks() if r.station == station]
        snap[station] = (unacked, acked[-1] if acked else None)
    return snap


def _qualifies(snap, change):
    unacked, held = snap[change.station]
    outstanding = any(change.time - OUTSTANDING_WINDOW < t <= change.time for t in unacked)
    return outstanding and change.price != held


def _run(seed, **options):
    importlib.reload(app)
    sim = Simulation(seed, **options)
    sim.connect(app)
    pending = []
    results = []
    while True:
        snap = _snapshot(sim)
        changes_before = len(sim.changes())
        sends_before = len(sim.sends())
        if not sim.step():
            break
        if len(sim.changes()) > changes_before:
            change = sim.changes()[-1]
            if _qualifies(snap, change):
                pending.append((change.station, change.time, sends_before))
        still = []
        for station, t, start in pending:
            sent = [r for r in sim.sends()[start:] if r.station == station]
            if sent:
                results.append((station, t, sent[0].sent_at))
            elif sim.now > t + BOUND:
                results.append((station, t, None))
            else:
                still.append((station, t, start))
        pending = still
    results += [(station, t, None) for station, t, _ in pending]
    return results


def _assert_bound(results):
    assert results, 'no change met the precondition (outstanding send, price differs from held)'
    for station, t, sent_at in results:
        assert sent_at is not None, f'{station}: change at {t} got no send'
        assert sent_at <= t + BOUND, f'{station}: change at {t} got its next send at {sent_at}'


def test_next_send_within_60_seconds_default_run():
    results = []
    for seed in SEEDS:
        results += _run(seed)
    _assert_bound(results)


def test_next_send_within_60_seconds_heavy_loss():
    results = []
    for seed in SEEDS:
        results += _run(seed, drop_probability=0.5)
    _assert_bound(results)


def test_next_send_within_60_seconds_no_loss():
    results = []
    for seed in SEEDS:
        results += _run(seed, drop_probability=0.0)
    _assert_bound(results)


def test_next_send_within_60_seconds_many_stations_and_bursts():
    results = []
    for seed in SEEDS:
        results += _run(seed, stations=('A', 'B', 'C', 'D'), changes=120, horizon=900.0)
    _assert_bound(results)
