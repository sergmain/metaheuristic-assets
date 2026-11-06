'''GASV4E2CK-33: an unacknowledged update is reported to the publisher every 30 logical seconds.

A report to the publisher is observed as a SendUpdate call for the station, the only outgoing port
the environment exposes. Criterion times are relative to the send. Station A's update is sent during
simulation second 2 and station B's during second 1, so criterion time T is second T+2 for A and T+1 for B.
'''

import app
from nrvv_env import SERVER_METHODS, Simulation

SEEDS = (1, 2, 3, 4, 5)


def _make_server(send_update):
    for name in dir(app):
        cls = getattr(app, name)
        if not (isinstance(cls, type) and name[:1].isupper() and cls.__module__.split('.')[0] == app.__name__):
            continue
        try:
            server = cls(send_update)
        except TypeError:
            server = cls()
        if all(callable(getattr(server, m, None)) for m in SERVER_METHODS):
            return server
    raise AssertionError('app provides no server class with the four server operations')


def _run(seed, horizon, changes, delivered):
    '''Runs the simulation to horizon. Downlink sends are delivered only in the seconds listed in delivered.'''
    sim = Simulation(seed, server=_make_server, stations=['A', 'B'], changes=changes, loss_uplink=0.0)
    while sim.now < horizon:
        sim.loss_downlink = 0.0 if sim.now + 1 in delivered else 1.0
        sim.step()
    return sim


def _sends(sim, station):
    return [tx.sent_at for tx in sim.transmissions if tx.station == station]


def _acked_by(sim, station, second):
    return any(a.delivered_at is not None and a.delivered_at <= second for a in sim.acks if a.station == station)


def test_unacknowledged_update_reported_at_30_and_60_seconds():
    for seed in SEEDS:
        # B's update (second 1) is delivered and acknowledged early; A's update (second 2) is never delivered.
        sim = _run(seed, 62, [(1, 'B', 5), (2, 'A', 3)], delivered={1})
        assert sim.stations['A'].received == [], seed
        assert _acked_by(sim, 'B', 31), seed
        # Sends to A at 2 (update), 32 (criterion 30 s), 62 (criterion 60 s); none in between.
        assert _sends(sim, 'A') == [2, 32, 62], seed
        # The acknowledged station B is never reported at or after its 30 s point.
        assert _sends(sim, 'B') == [1], seed


def test_acknowledged_update_is_never_reported():
    for seed in SEEDS:
        sim = _run(seed, 100, [(1, 'B', 5)], delivered={1})
        assert _acked_by(sim, 'B', 31), seed
        assert _sends(sim, 'B') == [1], seed


def test_silent_update_reported_every_30_seconds():
    for seed in SEEDS:
        sim = _run(seed, 122, [(2, 'A', 3)], delivered=set())
        assert sim.stations['A'].received == [], seed
        assert _sends(sim, 'A') == [2, 32, 62, 92, 122], seed
