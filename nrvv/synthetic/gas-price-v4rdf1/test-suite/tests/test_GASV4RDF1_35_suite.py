'''Tests for GASV4RDF1-3: each change of a desired price is sent to its station.'''

import app
import nrvv_env

SEEDS = (1, 2, 3, 4, 5)
SERVER_CONSTRUCTORS = ('Server', 'Service', 'StationServer', 'make_server', 'create_server')


def _make_server(send_update, send_pricing_notice):
    for name in SERVER_CONSTRUCTORS:
        constructor = getattr(app, name, None)
        if constructor is not None:
            return constructor(send_update, send_pricing_notice)
    raise AttributeError('app provides no server constructor')


def _run(seed, script, stations):
    sim = nrvv_env.Simulation(seed, _make_server, stations, script=script)
    sim.run(max_steps=10000)
    return sim


def _sent_to(sim, station, start, end=None):
    return [u for u in sim.sent
            if u.station == station and u.step >= start and (end is None or u.step < end)]


def _changes(sim, station):
    '''Each client call to the station, paired with the step where the next change to it begins.'''
    calls = [c for c in sim.client_calls if c.station == station]
    ends = [c.step for c in calls[1:]] + [None]
    return list(zip(calls, ends))


def _assert_each_change_answered(sim, station):
    for call, end in _changes(sim, station):
        answers = _sent_to(sim, station, call.step, end)
        assert any(u.price == call.price for u in answers), 'change to a price has no update carrying it'


def test_change_to_new_price_is_sent_with_new_price_not_previous():
    for seed in SEEDS:
        sim = _run(seed, [[('A', 10), ('A', 20)]], ['A'])
        _, second = sim.client_calls
        after = _sent_to(sim, 'A', second.step)
        assert after, 'no update sent to the station after the change'
        assert all(u.price == 20 for u in after), 'an update after the change carries the previous price'


def test_each_change_is_followed_by_update_carrying_that_price():
    for seed in SEEDS:
        sim = _run(seed, [[('A', 10), ('A', 20), ('A', 30)]], ['A'])
        _assert_each_change_answered(sim, 'A')


def test_change_is_answered_by_update_addressed_to_that_station():
    for seed in SEEDS:
        sim = _run(seed, [[('A', 10), ('B', 40), ('A', 20), ('B', 50)]], ['A', 'B'])
        _assert_each_change_answered(sim, 'A')
        _assert_each_change_answered(sim, 'B')


def test_no_update_carries_a_superseded_desired_price():
    for seed in SEEDS:
        sim = nrvv_env.Simulation(seed, _make_server, ['A', 'B', 'C'])
        sim.run(max_steps=10000)
        for update in sim.sent:
            desired = sim.desired_at(update.station, update.step)
            assert desired is None or update.price == desired, 'update carries a price other than the desired one'


def test_last_update_to_each_station_carries_its_latest_desired_price():
    for seed in SEEDS:
        sim = nrvv_env.Simulation(seed, _make_server, ['A', 'B', 'C'])
        sim.run(max_steps=10000)
        for station in ['A', 'B', 'C']:
            if not any(c.station == station for c in sim.client_calls):
                continue
            sent = _sent_to(sim, station, 0)
            assert sent, 'no update sent to a station that received a desired price'
            assert sent[-1].price == sim.latest_desired(station), 'last update does not carry the latest desired price'


def test_each_change_in_random_workload_is_answered():
    for seed in SEEDS:
        sim = nrvv_env.Simulation(seed, _make_server, ['A', 'B', 'C'])
        sim.run(max_steps=10000)
        for station in ['A', 'B', 'C']:
            _assert_each_change_answered(sim, station)
