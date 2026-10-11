'''Tests for GASV4ACCJ-2: every change of a station's desired gas price is published to that station.'''
import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)
ISOLATION = 90


def _server(ports):
    if hasattr(app, 'set_desired_price'):
        connect = getattr(app, 'connect', None)
        if connect is not None:
            connect(ports)
        return app
    for name in dir(app):
        obj = getattr(app, name)
        if isinstance(obj, type) and hasattr(obj, 'set_desired_price'):
            try:
                server = obj(ports)
            except TypeError:
                server = obj()
                connect = getattr(server, 'connect', None)
                if connect is not None:
                    connect(ports)
            return server
    raise AssertionError('app provides no object with set_desired_price')


def _run(seed):
    # Perfect transport: no loss and every station always reachable, so each
    # change must produce exactly one update and nothing is re-sent.
    sim = Simulation(seed, _server, horizon=1200, loss_rate=0.0)
    for station in sim.stations.values():
        station.unreachable = []
    sim.run_until_idle()
    sim.advance_to(sim.now + 120)
    return sim


def test_each_change_yields_exactly_one_update_to_its_station():
    changes_checked = 0
    for seed in SEEDS:
        sim = _run(seed)
        for sid in sim.stations:
            changes = [c for c in sim.changes if c.station_id == sid]
            updates = [s for s in sim.sends if s.station_id == sid]
            assert [u.price for u in updates] == [c.price for c in changes], (seed, sid)
            changes_checked += len(changes)
    assert changes_checked > 0


def test_isolated_change_is_followed_by_exactly_one_update_with_new_price():
    checked = 0
    for seed in SEEDS:
        sim = _run(seed)
        for sid in sim.stations:
            changes = [c for c in sim.changes if c.station_id == sid]
            for i, change in enumerate(changes):
                if i > 0 and change.time - changes[i - 1].time < ISOLATION:
                    continue
                if i + 1 < len(changes) and changes[i + 1].time - change.time < ISOLATION:
                    continue
                end = changes[i + 1].time if i + 1 < len(changes) else None
                window = [
                    s for s in sim.sends
                    if s.station_id == sid
                    and s.sent_at >= change.time
                    and (end is None or s.sent_at < end)
                ]
                assert len(window) == 1, (seed, sid, change.time)
                assert window[0].price == change.price, (seed, sid, change.time)
                checked += 1
    assert checked > 0
