'''Tests for GASV4RDF1-7: do not send updates to stations already on latest price.'''

import inspect

import app
import nrvv_env


REQUIRED_OPERATIONS = ('set_desired_price', 'receive_acknowledgement', 'query_station_state')


def _make_server(send_update, send_pricing_notice):
    for name in dir(app):
        candidate = getattr(app, name)
        if inspect.isclass(candidate) and all(
                callable(getattr(candidate, op, None)) for op in REQUIRED_OPERATIONS):
            return candidate(send_update, send_pricing_notice)
    raise AssertionError('app provides no server class with the required operations')


def _run_to_quiet(sim):
    sim.run(max_steps=10000)


def _updates_to(sim, station, since=0):
    return [update for update in sim.sent[since:] if update.station == station]


def test_no_update_sent_to_station_whose_acknowledged_price_equals_desired_price():
    for seed in range(10):
        for price in (1, 37, 100):
            sim = nrvv_env.Simulation(seed, _make_server, ['S1'], script=[[('S1', price)]])
            _run_to_quiet(sim)
            ack = sim.last_ack('S1')
            assert ack is not None and ack.price == price, (seed, price)
            assert sim.latest_desired('S1') == price, (seed, price)
            for _ in range(2):
                mark = len(sim.sent)
                sim.server.set_desired_price('S1', price)
                _run_to_quiet(sim)
                assert _updates_to(sim, 'S1', mark) == [], (seed, price)


def test_no_update_sent_to_settled_station_while_other_station_is_updated():
    for seed in range(10):
        sim = nrvv_env.Simulation(seed, _make_server, ['A', 'B'], script=[[('A', 25), ('B', 60)]])
        _run_to_quiet(sim)
        assert sim.last_ack('A') is not None and sim.last_ack('A').price == 25, seed
        assert sim.last_ack('B') is not None and sim.last_ack('B').price == 60, seed
        mark = len(sim.sent)
        sim.server.set_desired_price('A', 25)
        sim.server.set_desired_price('B', 61)
        _run_to_quiet(sim)
        assert _updates_to(sim, 'A', mark) == [], seed
        assert 61 in [update.price for update in _updates_to(sim, 'B', mark)], seed


def test_update_is_sent_when_desired_price_differs_from_acknowledged_price():
    for seed in range(10):
        sim = nrvv_env.Simulation(seed, _make_server, ['S1'], script=[[('S1', 10)]])
        _run_to_quiet(sim)
        mark = len(sim.sent)
        sim.server.set_desired_price('S1', 11)
        _run_to_quiet(sim)
        assert 11 in [update.price for update in _updates_to(sim, 'S1', mark)], seed
