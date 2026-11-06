'''Verifies GASV4ACCJ-36 (requirement GASV4ACCJ-17): after a desired-price change made
while a send from the same station is outstanding, the station's next send occurs at
or before t+60 seconds.'''
import app
from nrvv_env import Simulation

WINDOW = 60
ABANDON_AFTER = 30
SEEDS = range(1, 21)


def _run(seed, **kwargs):
    sim = Simulation(seed, app, **kwargs)
    sim.advance_to(sim.horizon + 100)
    return sim


def _is_outstanding(send, t):
    if send.sent_at >= t or t >= send.sent_at + ABANDON_AFTER:
        return False
    return send.ack_at is None or send.ack_at > t


def _held_price(sends, t):
    acked = [s for s in sends if s.ack_at is not None and s.ack_at <= t]
    return max(acked, key=lambda s: s.sent_at).price if acked else None


def _scenarios(sim):
    for change in sim.changes:
        t, sid = change.time, change.station_id
        sends = [s for s in sim.sends if s.station_id == sid]
        if any(s.sent_at == t for s in sends):
            continue
        if not any(_is_outstanding(s, t) for s in sends):
            continue
        if _held_price(sends, t) == change.price:
            continue
        later = [s.sent_at for s in sends if s.sent_at > t]
        yield change, (min(later) if later else None)


def _assert_bound(seeds, **kwargs):
    checked = 0
    late = []
    for seed in seeds:
        for change, next_send in _scenarios(_run(seed, **kwargs)):
            checked += 1
            if next_send is None or next_send > change.time + WINDOW:
                late.append((seed, change.station_id, change.time, next_send))
    assert checked > 0, 'no change met the criterion preconditions; scenario not exercised'
    assert not late, 'next send later than t+60 (seed, station, t, next_send): %r' % late


def test_next_send_within_60s_of_change_with_outstanding_send():
    _assert_bound(SEEDS)


def test_next_send_within_60s_on_lossless_transport():
    _assert_bound(SEEDS, loss_rate=0.0)


def test_next_send_within_60s_under_heavy_loss():
    _assert_bound(SEEDS, loss_rate=0.8)


def test_next_send_within_60s_with_single_station():
    _assert_bound(SEEDS, station_ids=('S1',))


def test_next_send_within_60s_with_five_stations():
    _assert_bound(SEEDS, station_ids=('S1', 'S2', 'S3', 'S4', 'S5'))


def test_next_send_within_60s_when_pricing_team_faults():
    _assert_bound(SEEDS, pricing_fault_rate=0.5)
