"""GASV4ELMA-35 (requirement GASV4ELMA-2): a new desired price is accepted while earlier updates are unacknowledged."""
import random

import app
from nrvv_env import PRICES, Simulation, check

ACCEPTED = 'Accepted'
SEEDS = range(5)


def _make_sim(seed):
    return Simulation(seed, server_factory=lambda dispatch: app.Server(dispatch_update=dispatch))


def _three_prices(seed):
    # three distinct prices, so each submission differs from the one before it
    return tuple(random.Random(seed).sample(PRICES, 3))


def _latest_desired(state):
    for name in ('latest_desired', 'latestDesired'):
        if isinstance(state, dict) and name in state:
            return state[name]
        if hasattr(state, name):
            return getattr(state, name)
    raise AssertionError('station state has no latest desired price: %r' % (state,))


def test_second_desired_price_accepted_while_first_is_unacknowledged():
    for seed in SEEDS:
        sim = _make_sim(seed)
        server = sim.app
        sid = sim.station_ids[0]
        first, second, _ = _three_prices(seed)

        assert server.set_desired_price(sid, first) == ACCEPTED
        # the first update went out and nothing has acknowledged it yet
        assert [r.price for r in sim.traffic('dispatch')] == [first]
        assert sim.traffic('ack') == []

        assert server.set_desired_price(sid, second) == ACCEPTED
        assert _latest_desired(server.station_state(sid)) == second


def test_third_desired_price_accepted_while_second_is_unacknowledged():
    for seed in SEEDS:
        sim = _make_sim(seed)
        server = sim.app
        sid = sim.station_ids[0]
        first, second, third = _three_prices(seed)

        assert server.set_desired_price(sid, first) == ACCEPTED
        assert server.set_desired_price(sid, second) == ACCEPTED
        assert sim.traffic('ack') == []
        assert _latest_desired(server.station_state(sid)) == second

        assert server.set_desired_price(sid, third) == ACCEPTED
        assert sim.traffic('ack') == []
        assert _latest_desired(server.station_state(sid)) == third


def test_scheduled_price_bursts_are_all_accepted_with_updates_in_flight():
    in_flight_sets = 0
    for seed in SEEDS:
        sim = _make_sim(seed)
        while True:
            before = len(sim.trace)
            if not sim.step():
                break
            if any(r.kind == 'set' for r in sim.trace[before:]) and sim.in_flight() > 0:
                in_flight_sets += 1
        results = check(sim)
        assert results['set_result'] == [], results['set_result']
    assert in_flight_sets > 0, 'no price change arrived while an update was in flight'
