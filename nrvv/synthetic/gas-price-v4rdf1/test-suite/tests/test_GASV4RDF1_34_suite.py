import inspect

import app
import nrvv_env


SEEDS = range(8)


def _server_class():
    candidates = [obj for obj in vars(app).values()
                  if inspect.isclass(obj) and callable(getattr(obj, 'set_desired_price', None))]
    assert len(candidates) == 1, 'app must define exactly one class with set_desired_price'
    return candidates[0]


def _make_server(send_update, send_pricing_notice):
    return _server_class()(send_update, send_pricing_notice)


def _state_values(state):
    if isinstance(state, dict):
        return list(state.values())
    if isinstance(state, (tuple, list)):
        return list(state)
    return list(vars(state).values())


def test_second_desired_price_accepted_while_first_unacknowledged():
    station = 'S1'
    overlapped = 0
    for seed in SEEDS:
        script = [[(station, 33), (station, 77)]]
        sim = nrvv_env.Simulation(seed, _make_server, [station], script=script, clients=1)
        while len(sim.client_calls) < 2:
            assert sim.step(), 'run went quiet before the second call was issued'
        second = sim.client_calls[1]
        assert second.station == station and second.price == 77
        if not sim.delivered_acks:
            overlapped += 1
        assert 77 in _state_values(sim.query(station)), (
            'second desired price was not accepted at once, seed %r' % seed)
        sim.run(max_steps=1000)
        assert 77 in _state_values(sim.query(station)), (
            'second desired price lost after run, seed %r' % seed)
    assert overlapped > 0, 'no seed issued the second call before the first update was acknowledged'


def test_every_desired_price_call_accepted_at_once_under_random_schedules():
    stations = ['S1', 'S2']
    for seed in SEEDS:
        sim = nrvv_env.Simulation(seed, _make_server, stations, clients=3, calls=10)
        seen = 0
        while sim.step():
            while seen < len(sim.client_calls):
                call = sim.client_calls[seen]
                seen += 1
                assert call.price in _state_values(sim.query(call.station)), (
                    'desired price %r not accepted at once, seed %r' % (call.price, seed))
        assert seen == 30, 'expected 30 client calls, saw %d, seed %r' % (seen, seed)
        assert sim.quiet, 'run did not reach quiet, seed %r' % seed
