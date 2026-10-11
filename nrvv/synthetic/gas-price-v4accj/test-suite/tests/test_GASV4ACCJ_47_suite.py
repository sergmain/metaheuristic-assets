import random

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)
EARLIER_AT = 1
NEW_AT = 4
NEWEST_AT = 5


def _prices(seed):
    rng = random.Random(seed)
    earlier = rng.randint(50, 99)
    new = rng.randint(100, 150)
    newest = new + rng.randint(1, 20)
    return earlier, new, newest


def _accepted(result):
    if result is None:
        return False
    if isinstance(result, bool):
        return result
    if isinstance(result, str):
        text = result.strip().lower()
        return 'accept' in text and 'reject' not in text
    accepted = getattr(result, 'accepted', None)
    if accepted is not None:
        return bool(accepted)
    if isinstance(result, dict):
        return bool(result.get('accepted', False))
    return True


def _read_field(status, *names):
    for name in names:
        if isinstance(status, dict) and name in status:
            return status[name]
        if hasattr(status, name):
            return getattr(status, name)
    raise AssertionError('status has none of %r: %r' % (names, status))


def _desired(station):
    return _read_field(app.query_station_status(station), 'desired_price', 'desired')


def _unacknowledged_send(sim, station):
    sent = [s for s in sim.sends if s.station_id == station]
    acked = [a for a in sim.acks if a.station_id == station]
    return bool(sent) and not acked


def _change_at(run, when):
    matches = [c for c in run['sim'].changes if c.time == when and c.station_id == run['station']]
    assert len(matches) == 1, 'change for %s was not dispatched at second %d' % (run['station'], when)
    return matches[0]


def _run(tag, seed):
    station = '%s-%d' % (tag, seed)
    earlier, new, newest = _prices(seed)
    sim = Simulation(seed, app, station_ids=(station,), horizon=0, loss_rate=1.0)
    sim._push(EARLIER_AT, 'change', (station, earlier))
    sim.advance_to(NEW_AT - 1)
    assert _unacknowledged_send(sim, station), 'earlier update must be sent and still unacknowledged'
    run = {'sim': sim, 'station': station, 'new': new, 'newest': newest}
    sim._push(NEW_AT, 'change', (station, new))
    sim.advance_to(NEW_AT)
    run['after_new'] = _desired(station)
    sim._push(NEWEST_AT, 'change', (station, newest))
    sim.advance_to(NEWEST_AT)
    run['after_newest'] = _desired(station)
    return run


def test_new_price_accepted_at_once_while_earlier_update_unacknowledged():
    for seed in SEEDS:
        run = _run('intake', seed)
        change = _change_at(run, NEW_AT)
        assert change.price == run['new']
        assert change.time == NEW_AT
        assert _accepted(change.result), 'new price rejected: %r' % (change.result,)


def test_reading_desired_price_returns_new_value_after_submission():
    for seed in SEEDS:
        run = _run('readback', seed)
        assert run['after_new'] == run['new']


def test_second_price_accepted_at_once_and_only_latest_is_read():
    for seed in SEEDS:
        run = _run('latest', seed)
        change = _change_at(run, NEWEST_AT)
        assert change.price == run['newest']
        assert change.time == NEWEST_AT
        assert _accepted(change.result), 'second new price rejected: %r' % (change.result,)
        assert run['after_newest'] == run['newest']
        assert run['after_newest'] != run['new']
