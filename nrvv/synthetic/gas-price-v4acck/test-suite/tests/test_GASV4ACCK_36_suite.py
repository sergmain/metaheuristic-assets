'''GASV4ACCK-36: dispatch decision when the confirmed price is stale (GASV4ACCK-13).'''

import random

import app
from nrvv_env import Simulation

STATION = 'station-1'
SEEDS = (1, 2, 3)


def _server_class():
    for value in vars(app).values():
        if isinstance(value, type) and hasattr(value, 'set_latest_price'):
            return value
    raise AssertionError('app defines no class with set_latest_price')


def _make_server(seed):
    sim = Simulation(seed, [STATION])
    server_cls = _server_class()
    try:
        server = server_cls()
    except TypeError:
        server = server_cls(sim.send_price_update)
    sim.bind(server)
    return sim, server


def _pick(view, names):
    for name in names:
        if isinstance(view, dict):
            if name in view:
                return view[name]
        elif hasattr(view, name):
            return getattr(view, name)
    raise AssertionError(f'station view lacks {names[0]}')


def _view_prices(server):
    view = server.get_station_view(STATION)
    latest = _pick(view, ('latest_price', 'latest'))
    acked = _pick(view, ('last_acknowledged_price', 'acknowledged_price', 'last_acked_price'))
    outstanding = _pick(view, ('outstanding_price', 'outstanding'))
    if hasattr(outstanding, 'price'):
        outstanding = outstanding.price
    return latest, acked, outstanding


def _assert_dispatched(sim, before, server, price):
    new = sim.sends[before:]
    assert len(new) == 1, f'expected one dispatch, got {len(new)}'
    assert new[0].station == STATION
    assert new[0].price == price
    latest, _, outstanding = _view_prices(server)
    assert latest == price
    assert outstanding == price


def _assert_quiet(sim, before, server, outstanding):
    assert len(sim.sends) == before, 'dispatch while an update is outstanding'
    assert _view_prices(server)[2] == outstanding


def test_each_state_change_dispatches_latest_price_and_blocks_while_outstanding():
    for seed in SEEDS:
        sim, server = _make_server(seed)
        p1, p2, p3 = random.Random(seed).sample(range(1, 1000), 3)
        now = 0

        # trigger: set a new latest price on a fresh station
        before = len(sim.sends)
        server.set_latest_price(STATION, p1)
        _assert_dispatched(sim, before, server, p1)

        # while p1 is outstanding: advance the clock, then set another price
        now += 1
        before = len(sim.sends)
        server.tick(now)
        _assert_quiet(sim, before, server, p1)
        server.set_latest_price(STATION, p2)
        _assert_quiet(sim, before, server, p1)

        # trigger: acknowledgement releases p2 as the next update
        before = len(sim.sends)
        server.acknowledgement_received(STATION)
        assert _view_prices(server)[1] == p1
        _assert_dispatched(sim, before, server, p2)

        # while p2 is outstanding: set another price, then advance the clock
        before = len(sim.sends)
        server.set_latest_price(STATION, p3)
        _assert_quiet(sim, before, server, p2)
        now += 1
        server.tick(now)
        _assert_quiet(sim, before, server, p2)

        # trigger: acknowledgement releases p3
        before = len(sim.sends)
        server.acknowledgement_received(STATION)
        assert _view_prices(server)[1] == p2
        _assert_dispatched(sim, before, server, p3)

        # while p3 is outstanding: advance the clock
        before = len(sim.sends)
        now += 1
        server.tick(now)
        _assert_quiet(sim, before, server, p3)
