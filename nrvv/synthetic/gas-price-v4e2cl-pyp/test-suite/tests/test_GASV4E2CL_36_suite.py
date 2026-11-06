'''Suite for GASV4E2CL-36 (requirement GASV4E2CL-10): desired-price acceptance is never gated.'''
from collections.abc import Mapping

import app
from nrvv_env import Simulation

STATION = 'S1'
SEEDS = (1, 2, 3)


def _make_server(send_price_update):
    for name, obj in vars(app).items():
        if name.startswith('_') or not isinstance(obj, type):
            continue
        try:
            server = obj(send_price_update)
        except Exception:
            continue
        if hasattr(server, 'set_desired_price'):
            return server
    raise AssertionError('app provides no server class constructible from the send port')


def _field(view, name):
    if isinstance(view, Mapping):
        return view[name]
    return getattr(view, name)


def _version(sim):
    return _field(sim.server.observe_station(STATION), 'desired_version')


def _accepted(result):
    if result is None:
        return True
    if isinstance(result, bool):
        return result
    text = str(getattr(result, 'name', result)).lower()
    return 'accept' in text and not any(w in text for w in ('reject', 'defer', 'block'))


def _check_new_price_then_repeat(sim, new_price):
    server = sim.server
    before = _version(sim)
    result = server.set_desired_price(STATION, new_price)
    assert _accepted(result), f'new price {new_price} not accepted: {result!r}'
    assert sim.desired_price(STATION) == new_price
    assert _version(sim) == before + 1
    version = _version(sim)
    sends = len(sim.sends)
    to_station = len(sim.to_station)
    result = server.set_desired_price(STATION, new_price)
    assert _accepted(result), f'repeated price {new_price} not accepted: {result!r}'
    assert sim.desired_price(STATION) == new_price
    assert _version(sim) == version
    assert len(sim.sends) == sends
    assert len(sim.to_station) == to_station


def test_new_price_accepted_while_update_in_flight():
    for seed in SEEDS:
        sim = Simulation(seed, _make_server, duration=0)
        sim.server.set_desired_price(STATION, 100 + seed)
        assert sim.sends, 'earlier update was not dispatched'
        assert sim.in_flight() > 0, 'earlier update is not in flight'
        _check_new_price_then_repeat(sim, 500 + seed)


def test_new_price_accepted_while_update_unacknowledged():
    for seed in SEEDS:
        sim = Simulation(seed, _make_server, duration=0)
        sim.server.set_desired_price(STATION, 100 + seed)
        while not sim.stations[STATION].received:
            assert sim.step(), 'earlier update was never delivered'
        assert sim.from_station and sim.from_station[-1].delivered_at is None, 'acknowledgement already delivered'
        _check_new_price_then_repeat(sim, 500 + seed)
