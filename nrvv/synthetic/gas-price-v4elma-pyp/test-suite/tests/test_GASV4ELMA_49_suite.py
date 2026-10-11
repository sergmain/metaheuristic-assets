'''GASV4ELMA-49: the latest price reaches a station that is never changed.'''
from collections import Counter

import app
from nrvv_env import Simulation, Station, check

SEEDS = (1, 2, 3, 5, 8, 13, 21, 34)
BOUND = 10.0


def _server(dispatch_update):
    return app.Server(dispatch_update=dispatch_update)


def _run(seed, **kwargs):
    sim = Simulation(seed=seed, server_factory=_server, **kwargs)
    sim.run()
    return sim


def test_latest_price_is_displayed_after_random_runs():
    for seed in SEEDS:
        violations = {k: v for k, v in check(_run(seed), convergence_bound=BOUND).items() if v}
        assert not violations, 'seed %d: %r' % (seed, violations)


def test_correction_replaces_earlier_price_on_same_station():
    corrections = 0
    for seed in SEEDS:
        sim = Simulation(seed=seed, server_factory=_server)
        for sid in sim.station_ids:
            sim.force_reachable(sid, 0.0)
        sim.run()
        latest = {}
        for r in sim.traffic('set'):
            if r.station in latest and latest[r.station] != r.price:
                corrections += 1
            latest[r.station] = r.price
        for sid, price in latest.items():
            shown = sim.stations[sid].display
            assert shown == price, 'seed %d station %s: shows %r, latest %r' % (seed, sid, shown, price)
    assert corrections > 0


def test_station_software_and_configuration_are_unchanged():
    sim = Simulation(seed=4, server_factory=_server)
    class_before = dict(vars(Station))
    attrs_before = {sid: sorted(vars(st)) for sid, st in sim.stations.items()}
    sim.run()
    assert dict(vars(Station)) == class_before
    for sid, st in sim.stations.items():
        assert st.station_id == sid
        assert sorted(vars(st)) == attrs_before[sid]


def test_station_shows_each_price_it_receives():
    for seed in SEEDS:
        sim = _run(seed)
        prev = None
        for r in sim.trace:
            if r.kind == 'display':
                assert prev is not None and prev.kind == 'deliver'
                assert (prev.station, prev.seq, prev.price) == (r.station, r.seq, r.price)
            prev = r


def test_station_receives_only_service_updates():
    for seed in SEEDS:
        sim = _run(seed)
        dispatched = Counter((r.station, r.seq, r.price) for r in sim.traffic('dispatch'))
        delivered = Counter((r.station, r.seq, r.price) for r in sim.traffic('deliver'))
        assert not (delivered - dispatched), 'seed %d: delivery without dispatch' % seed


def test_convergence_holds_for_other_station_counts():
    for stations in (1, 5):
        for seed in SEEDS[:4]:
            violations = {k: v for k, v in check(_run(seed, stations=stations), convergence_bound=BOUND).items() if v}
            assert not violations, 'stations %d seed %d: %r' % (stations, seed, violations)
