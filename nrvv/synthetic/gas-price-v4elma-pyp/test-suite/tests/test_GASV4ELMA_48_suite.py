"""Tests for GASV4ELMA-48 / GASV4ELMA-11: desired-price arrival is always accepted and overwrites the slot."""
import app
from nrvv_env import PRICES, Simulation, check

STATION = 'station-1'
P1, P2 = PRICES[0], PRICES[1]
SEEDS = (0, 1, 2, 3, 4)


def _server(dispatch):
    return app.Server(dispatch_update=dispatch)


def _quiet_sim(seed):
    # no scheduled price changes; the station is reachable for the whole run
    sim = Simulation(seed=seed, server_factory=_server, stations=1, stop_time=0.0)
    sim.force_reachable(STATION, 0.0)
    return sim


def _field(state, *names):
    for name in names:
        if isinstance(state, dict):
            if name in state:
                return state[name]
        elif hasattr(state, name):
            return getattr(state, name)
    raise AssertionError('StationState has none of the fields %s' % (names,))


def _latest(sim):
    return _field(sim.app.station_state(STATION), 'latest_desired', 'latestDesired')


def _last_sent(sim):
    return _field(sim.app.station_state(STATION), 'last_sent_price', 'lastSentPrice')


def _dispatches(sim):
    return sim.traffic('dispatch')


def test_overwrite_while_outstanding_accepts_and_keeps_only_new_price():
    for seed in SEEDS:
        sim = _quiet_sim(seed)
        assert sim.app.set_desired_price(STATION, P1) == 'Accepted'
        assert sim.in_flight() > 0, 'P1 must be outstanding before the overwrite'
        assert _latest(sim) == P1

        sent_before = len(_dispatches(sim))
        assert sim.app.set_desired_price(STATION, P2) == 'Accepted'
        assert _latest(sim) == P2

        # same price again while P2 updates are still outstanding
        sent_after_first = len(_dispatches(sim))
        assert sim.app.set_desired_price(STATION, P2) == 'Accepted'
        assert _latest(sim) == P2
        assert len(_dispatches(sim)) == sent_after_first, 'same price must dispatch nothing'

        sim.run()
        assert _latest(sim) == P2
        assert _last_sent(sim) == P2, 'P1 must no longer be retained as the sent price'
        assert all(r.price != P1 for r in _dispatches(sim)[sent_before:]), \
            'P1 must not be dispatched after the overwrite'
        assert sim.stations[STATION].display == P2


def test_same_price_while_outstanding_dispatches_nothing():
    for seed in SEEDS:
        sim = _quiet_sim(seed)
        assert sim.app.set_desired_price(STATION, P1) == 'Accepted'
        assert sim.in_flight() > 0, 'P1 must be outstanding before the repeat'
        sent = len(_dispatches(sim))
        for _ in range(3):
            assert sim.app.set_desired_price(STATION, P1) == 'Accepted'
        assert _latest(sim) == P1
        assert len(_dispatches(sim)) == sent, 'same price must dispatch nothing'
        sim.run()
        assert sim.stations[STATION].display == P1


def test_burst_overwrites_are_accepted_and_only_latest_is_sent():
    seen_outstanding = 0
    for seed in (1, 2, 3, 4, 5):
        sim = Simulation(seed=seed, server_factory=_server, stations=3, stop_time=30.0)
        while True:
            pending = sim.in_flight()
            mark = len(sim.trace)
            if not sim.step():
                break
            if pending and any(r.kind == 'set' for r in sim.trace[mark:]):
                seen_outstanding += 1
        report = check(sim)
        for key in ('set_result', 'r6_latest_price', 'r4_r5_repeat',
                    'r7_unreachable_dispatch', 'sequence'):
            assert not report[key], '%s: %s' % (key, report[key][:3])
    assert seen_outstanding > 0, 'no desired-price call arrived while updates were outstanding'
