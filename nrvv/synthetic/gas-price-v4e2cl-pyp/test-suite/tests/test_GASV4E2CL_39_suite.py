import inspect
from collections.abc import Mapping

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)
REFUSAL_WORDS = ('reject', 'refus', 'block', 'error', 'fail', 'denied')


def _server_class():
    for name in dir(app):
        obj = getattr(app, name)
        if inspect.isclass(obj) and callable(getattr(obj, 'set_desired_price', None)):
            return obj
    raise AssertionError('app defines no class with set_desired_price')


def _make_server(send_price_update):
    cls = _server_class()
    attempts = (
        lambda: cls(send_price_update),
        lambda: cls(send_price_update=send_price_update),
        lambda: cls(send=send_price_update),
    )
    for attempt in attempts:
        try:
            return attempt()
        except TypeError:
            continue
    raise AssertionError('app server class cannot be built from the send port')


def _accepted(result):
    if result is None or result is False:
        return False
    if isinstance(result, str):
        return not any(word in result.lower() for word in REFUSAL_WORDS)
    if isinstance(result, Mapping):
        return bool(result.get('accepted', True))
    return bool(getattr(result, 'accepted', True))


def _run(seed):
    sim = Simulation(seed, _make_server)
    desired_after = {}
    while sim.step():
        if len(desired_after) < len(sim.changes):
            index = len(sim.changes) - 1
            desired_after[index] = sim.desired_price(sim.changes[index].station)
    return sim, desired_after


def _unacked_at(sim, send, time):
    acks = [m for m in sim.from_station
            if m.station == send.station and m.update_id == send.update_id]
    return not any(m.delivered_at is not None and m.delivered_at <= time for m in acks)


def _second_changes(sim):
    '''Indexes of changes made while an earlier, different price of the station is unacknowledged.'''
    found = []
    for i, change in enumerate(sim.changes):
        earlier = [c for c in sim.changes[:i] if c.station == change.station]
        if not earlier or earlier[-1].value == change.value:
            continue
        first = earlier[-1].value
        if any(s.station == change.station and s.price == first and s.time < change.time
               and _unacked_at(sim, s, change.time) for s in sim.sends):
            found.append(i)
    return found


def test_second_price_is_accepted_while_first_update_unacknowledged():
    checked = 0
    for seed in SEEDS:
        sim, _ = _run(seed)
        for i in _second_changes(sim):
            checked += 1
            change = sim.changes[i]
            assert _accepted(change.result), (
                f'seed {seed}: {change.value} to {change.station} at t={change.time} '
                f'refused with {change.result!r}')
    assert checked > 0


def test_second_price_is_recorded_as_station_desired_price():
    checked = 0
    for seed in SEEDS:
        sim, desired_after = _run(seed)
        for i in _second_changes(sim):
            checked += 1
            change = sim.changes[i]
            assert desired_after[i] == change.value, (
                f'seed {seed}: {change.value} to {change.station} at t={change.time} '
                f'recorded as {desired_after[i]!r}')
    assert checked > 0
