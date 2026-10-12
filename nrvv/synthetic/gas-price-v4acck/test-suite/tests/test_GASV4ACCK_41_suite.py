'''GASV4ACCK-17: once price changes stop, a single station converges to the final latest price.

Drives app only through nrvv_env. Every logical step is checked against the environment's
send, delivery and acknowledgement logs and against the station view that the server
exposes through get_station_view.
'''

import app
from nrvv_env import MAX_DELAY, Simulation

STATION = 'station-1'
ROUND_TRIP = 2 * MAX_DELAY  # a delivery and its acknowledgement each take at most MAX_DELAY
SEEDS = range(20)


def _make_server():
    if callable(getattr(app, 'set_latest_price', None)):
        return app
    for name in dir(app):
        candidate = getattr(app, name)
        if isinstance(candidate, type) and callable(getattr(candidate, 'set_latest_price', None)):
            return candidate()
    raise AssertionError('app provides no server with set_latest_price')


def _field(view, *names):
    for name in names:
        if isinstance(view, dict) and name in view:
            return view[name]
        if hasattr(view, name):
            return getattr(view, name)
    raise AssertionError(f'station view {view!r} has none of the fields {names}')


def _latest(view):
    return _field(view, 'latest_price', 'latest')


def _acknowledged(view):
    return _field(view, 'last_acknowledged_price', 'last_acked_price')


def _outstanding(view):
    value = _field(view, 'outstanding_price', 'outstanding')
    if isinstance(value, dict):
        return value['price']
    if value is not None and hasattr(value, 'price'):
        return value.price
    return value


def _step_checked(sim, server, outcomes):
    '''One logical step, then the dispatch rule checked at any acknowledgement in it.'''
    acks_before = len(sim.acknowledgements)
    changes_before = len(sim.changes)
    sends_before = len(sim.sends)
    t = sim.step()
    view = server.get_station_view(STATION)
    new_acks = len(sim.acknowledgements) - acks_before
    if new_acks == 0:
        return view
    acked = [r for r in sim.sends if r.acknowledged_at == t]
    assert len(acked) == new_acks, 'acknowledgement not recorded against a send'
    acked_price = acked[-1].price
    assert _acknowledged(view) == acked_price, (
        f'last-acknowledged price {_acknowledged(view)!r} != acknowledged {acked_price!r} at t={t}')
    if len(sim.changes) == changes_before:
        latest = _latest(view)
        if latest != acked_price:
            assert _outstanding(view) == latest, f'latest {latest!r} not dispatched at t={t}'
        else:
            assert _outstanding(view) is None, f'nothing should be outstanding at t={t}'
        if new_acks == 1:
            sent = [r.price for r in sim.sends[sends_before:]]
            if latest != acked_price:
                assert sent == [latest], f'expected dispatch of {latest!r} at t={t}, got {sent!r}'
                outcomes.append('differs')
            else:
                assert sent == [], f'price {latest!r} sent although it equals last-acknowledged at t={t}'
                outcomes.append('same')
    return view


def _converge(seed, **kwargs):
    '''Run one seed to convergence, checking every step; returns the dispatch outcomes seen.'''
    sim = Simulation(seed, [STATION], **kwargs)
    server = sim.bind(_make_server())
    outcomes = []
    # all changes fall within [0, window], so once that window is processed no more changes arrive
    while sim.now <= sim.window:
        _step_checked(sim, server, outcomes)
    final = sim.changes[-1].price
    assert final == sim.reference_final_prices[STATION]
    pending = sim.unacknowledged_sends()
    while sim.unacknowledged_sends():
        assert sim.now <= sim.window + 2 * ROUND_TRIP, \
            'outstanding updates not settled within two round trips of the last change'
        _step_checked(sim, server, outcomes)
    for record in pending:
        assert record.acknowledged_at is not None and record.acknowledged_at <= sim.window + ROUND_TRIP, \
            'outstanding update not acknowledged within the round-trip bound'
    view = server.get_station_view(STATION)
    assert _latest(view) == final, f'pending slot {_latest(view)!r} != final price {final!r}'
    last_processed = sim.now - 1
    while sim.now <= last_processed + ROUND_TRIP:
        _step_checked(sim, server, outcomes)
    view = server.get_station_view(STATION)
    assert _acknowledged(view) == final, f'last-acknowledged {_acknowledged(view)!r} != {final!r}'
    assert sim.stations[STATION].held_price == final, 'station does not hold the final price'
    assert _latest(view) == final
    return outcomes


def test_latest_and_last_acknowledged_price_converge_to_final_price():
    outcomes = [o for seed in SEEDS for o in _converge(seed)]
    assert 'differs' in outcomes


def test_acknowledgement_dispatches_latest_only_when_it_differs_from_last_acknowledged():
    outcomes = [o for seed in SEEDS
                for o in _converge(seed, changes_per_station=(2, 6), price_range=(1, 2))]
    assert 'differs' in outcomes and 'same' in outcomes


def test_frequent_changes_settle_on_final_price():
    for seed in range(20, 30):
        _converge(seed, changes_per_station=(5, 12))


def test_single_change_settles_on_that_price():
    for seed in range(30, 40):
        _converge(seed, changes_per_station=(1, 1))
