"""GASV4ELMA-34: a second desired price for a station replaces the first (GASV4ELMA-3)."""
import app
from nrvv_env import Simulation, check

PRICE_FIRST = '1.50'
PRICE_SECOND = '1.75'
SEEDS = (1, 2, 3, 4, 5)


def _server(dispatch):
    return app.Server(dispatch_update=dispatch)


def _quiet(seed, stations=3):
    # no scheduled price changes and no reachability changes: only the calls made by the test act
    return Simulation(seed=seed, server_factory=_server, stations=stations, stop_time=0.0, horizon=0.0)


def _field(state, *names):
    for name in names:
        if isinstance(state, dict) and name in state:
            return state[name]
        if hasattr(state, name):
            return getattr(state, name)
    raise AssertionError('station state has none of the fields %s' % (names,))


def _latest(state):
    return _field(state, 'latestDesired', 'latest_desired')


def test_second_desired_price_replaces_first_for_station():
    sim = _quiet(seed=1)
    sid = sim.station_ids[0]
    assert sim.app.set_desired_price(sid, PRICE_FIRST) == 'Accepted'
    assert sim.app.set_desired_price(sid, PRICE_SECOND) == 'Accepted'
    latest = _latest(sim.app.station_state(sid))
    assert isinstance(latest, str)
    assert latest == PRICE_SECOND
    sim.run()
    assert _latest(sim.app.station_state(sid)) == PRICE_SECOND
    assert sim.stations[sid].display == PRICE_SECOND
    assert not any(check(sim).values())


def test_replacement_affects_only_its_own_station_across_seeds():
    for seed in SEEDS:
        sim = _quiet(seed=seed)
        target, others = sim.station_ids[0], sim.station_ids[1:]
        for sid in sim.station_ids:
            assert sim.app.set_desired_price(sid, PRICE_FIRST) == 'Accepted'
        assert sim.app.set_desired_price(target, PRICE_SECOND) == 'Accepted'
        assert _latest(sim.app.station_state(target)) == PRICE_SECOND
        for sid in others:
            assert _latest(sim.app.station_state(sid)) == PRICE_FIRST
        sim.run()
        assert sim.stations[target].display == PRICE_SECOND
        for sid in others:
            assert sim.stations[sid].display == PRICE_FIRST
        assert not any(check(sim).values())


def test_each_new_price_replaces_the_previous_one_across_seeds():
    for seed in SEEDS:
        sim = _quiet(seed=seed)
        sid = sim.station_ids[0]
        for price in (PRICE_FIRST, '1.60', PRICE_SECOND):
            assert sim.app.set_desired_price(sid, price) == 'Accepted'
            assert _latest(sim.app.station_state(sid)) == price
        sim.run()
        assert _latest(sim.app.station_state(sid)) == PRICE_SECOND
        assert sim.stations[sid].display == PRICE_SECOND
        assert not any(check(sim).values())
