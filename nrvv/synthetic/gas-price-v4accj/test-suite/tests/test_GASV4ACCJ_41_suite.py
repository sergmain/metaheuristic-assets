'''GASV4ACCJ-41: a changed desired price is sent to the station within 120 s,
and a price the station has already acknowledged is not sent again.

Everything goes through nrvv_env: the simulation drives app and records the
messages the server sends (sim.sends), the acknowledgements that reach the
server (sim.acks) and the desired price changes (sim.changes).
'''
from nrvv_env import Simulation

import app

WINDOW = 120
HORIZON = 1200
END = HORIZON + 200
SEEDS = range(30)


def _run(seed, **options):
    sim = Simulation(seed, app, horizon=HORIZON, **options)
    sim.advance_to(END)
    return sim


def _next_change_time(sim, sid, t):
    later = [c.time for c in sim.changes if c.station_id == sid and c.time > t]
    return min(later) if later else END


def _superseded(sim, change):
    return any(
        other is not change and other.station_id == change.station_id
        and change.time <= other.time <= change.time + WINDOW
        for other in sim.changes
    )


def _sent_before(sim, sid, price, t):
    return any(s.station_id == sid and s.price == price and s.sent_at < t for s in sim.sends)


def _returns_to_acknowledged(sim, change):
    sid, price, t = change.station_id, change.price, change.time
    acks = [a for a in sim.acks if a.station_id == sid and a.time < t]
    if not acks:
        return False
    matches = [s for s in sim.sends if s.station_id == sid and s.send_id == acks[-1].send_id]
    if len(matches) != 1 or matches[0].price != price:
        return False
    after = sim.sends[sim.sends.index(matches[0]) + 1:]
    return all(s.outcome != 'delivered' for s in after if s.station_id == sid and s.sent_at < t)


def _check_new_price_sent(seed, **options):
    checked = 0
    sim = _run(seed, **options)
    for change in sim.changes:
        sid, price, t = change.station_id, change.price, change.time
        if _sent_before(sim, sid, price, t) or _superseded(sim, change):
            continue
        checked += 1
        sent = [
            s for s in sim.sends
            if s.station_id == sid and s.price == price and t <= s.sent_at <= t + WINDOW
        ]
        assert sent, f'seed {seed}: price {price} for {sid} set at {t} not sent within {WINDOW} s'
    return checked


def _check_acknowledged_not_resent(seed):
    checked = 0
    sim = _run(seed)
    for change in sim.changes:
        sid, price, t = change.station_id, change.price, change.time
        if not _returns_to_acknowledged(sim, change):
            continue
        checked += 1
        end = _next_change_time(sim, sid, t)
        resent = [
            s for s in sim.sends
            if s.station_id == sid and s.price == price and t <= s.sent_at < end
        ]
        assert not resent, f'seed {seed}: acknowledged price {price} for {sid} re-sent after being set at {t}'
    return checked


def test_new_price_is_sent_to_station_within_120_seconds():
    checked = sum(_check_new_price_sent(seed) for seed in SEEDS)
    assert checked > 0


def test_new_price_is_sent_within_120_seconds_on_lossless_transport():
    checked = sum(
        _check_new_price_sent(seed, loss_rate=0.0, station_ids=('A', 'B', 'C', 'D'))
        for seed in SEEDS
    )
    assert checked > 0


def test_acknowledged_price_is_not_sent_again():
    checked = sum(_check_acknowledged_not_resent(seed) for seed in SEEDS)
    assert checked > 0
