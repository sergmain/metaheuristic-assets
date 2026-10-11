'''Requirement GASV4ACCJ-13: at most one outstanding send per station.

Test case GASV4ACCJ-38. Drives the server only through nrvv_env.
'''
import importlib

import app
from nrvv_env import Simulation

STATION = 'S1'
FIRST_PRICE = 60
SECOND_PRICE = 120
ABANDON_AFTER = 30  # D5 timeout in seconds
SLOT = 60  # D7 slot in seconds
_OUTSTANDING_FIELDS = ('outstanding', 'outstanding_send', 'unresolved', 'unresolved_sends')


def _fresh_sim(seed, station_ids=(STATION,), loss_rate=0.0):
    # Reload so that no server state leaks between simulations.
    server = importlib.reload(app)
    return Simulation(seed, server, station_ids=station_ids, horizon=0, loss_rate=loss_rate)


def _reachable_sim(window, loss_rate):
    # Pick a seed whose station is reachable for the first `window` seconds,
    # so that a send can be delivered and acknowledged.
    for seed in range(1, 200):
        sim = _fresh_sim(seed, loss_rate=loss_rate)
        if all(sim.is_reachable(STATION, t) for t in range(window)):
            return sim
    raise AssertionError('no seed keeps the station reachable')


def _schedule(sim, when, station_id, price):
    # Submit an update through the environment's own change source.
    sim._push(when, 'change', (station_id, price))


def _step_until(sim, done, limit):
    while not done():
        if sim.now >= limit:
            raise AssertionError('condition not reached by second %d' % limit)
        sim.step()


def _sends(sim, station_id=STATION):
    return [s for s in sim.sends if s.station_id == station_id]


def _sends_at_price(sim, price):
    return [s for s in _sends(sim) if s.price == price]


def _acked_ids(sim):
    return {a.send_id for a in sim.acks}


def _unresolved_count(status):
    for name in _OUTSTANDING_FIELDS:
        if isinstance(status, dict) and name in status:
            value = status[name]
            break
        if not isinstance(status, dict) and hasattr(status, name):
            value = getattr(status, name)
            break
    else:
        raise AssertionError('station status shows no outstanding send: %r' % (status,))
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple, set, frozenset)):
        return len(value)
    return 1


def test_second_update_held_while_first_send_outstanding():
    for seed in (1, 2, 3):
        # Every send is lost, so the first send stays unresolved until its timeout.
        sim = _fresh_sim(seed, loss_rate=1.0)
        _schedule(sim, 1, STATION, FIRST_PRICE)
        _step_until(sim, lambda: bool(_sends(sim)), limit=10)
        first = _sends(sim)[0]
        _schedule(sim, sim.now + 2, STATION, SECOND_PRICE)
        while sim.now < first.sent_at + ABANDON_AFTER - 1:
            sim.step()
            assert len(_sends(sim)) == 1, 'second send transmitted while first is outstanding'
            assert _unresolved_count(app.query_station_status(STATION)) == 1
        assert any(c.price == SECOND_PRICE for c in sim.changes), 'second update never submitted'


def test_second_update_sent_after_first_send_acknowledged():
    sim = _reachable_sim(window=120, loss_rate=0.0)
    _schedule(sim, 1, STATION, FIRST_PRICE)
    _step_until(sim, lambda: bool(_sends(sim)), limit=10)
    first = _sends(sim)[0]
    assert first.outcome == 'delivered'
    _step_until(sim, lambda: first.send_id in _acked_ids(sim), limit=first.sent_at + ABANDON_AFTER)
    _schedule(sim, sim.now + 1, STATION, SECOND_PRICE)
    _step_until(sim, lambda: bool(_sends_at_price(sim, SECOND_PRICE)), limit=sim.now + SLOT * 2)
    assert len(_sends_at_price(sim, SECOND_PRICE)) == 1


def test_unacknowledged_send_abandoned_at_timeout_then_second_update_sent():
    for seed in (1, 2, 3):
        sim = _fresh_sim(seed, loss_rate=1.0)  # no acknowledgement ever comes back
        _schedule(sim, 1, STATION, FIRST_PRICE)
        _step_until(sim, lambda: bool(_sends(sim)), limit=10)
        first = _sends(sim)[0]
        _schedule(sim, sim.now + 1, STATION, SECOND_PRICE)
        _step_until(sim, lambda: bool(_sends_at_price(sim, SECOND_PRICE)),
                    limit=first.sent_at + ABANDON_AFTER + SLOT * 2)
        second = _sends_at_price(sim, SECOND_PRICE)[0]
        assert second.sent_at >= first.sent_at + ABANDON_AFTER, 'second send before the first timed out'


def test_outstanding_send_to_one_station_does_not_hold_another_station():
    sim = _fresh_sim(1, station_ids=('S1', 'S2'), loss_rate=1.0)
    _schedule(sim, 1, 'S1', FIRST_PRICE)
    _schedule(sim, 2, 'S2', FIRST_PRICE)
    _schedule(sim, 3, 'S1', SECOND_PRICE)
    _step_until(sim, lambda: bool(_sends(sim, 'S2')), limit=10)
    sim.advance_to(5)
    assert len(_sends(sim, 'S1')) == 1, 'second update for S1 sent while its first is outstanding'
    assert len(_sends(sim, 'S2')) == 1
