import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)
P = 10
Q = 20


def _sim(seed):
    return Simulation(app, seed, stations=('S1',), loss=0.0, outage=0.0)


def _establish_confirmed(sim, price):
    sim.set_desired_price('S1', price)
    assert sim.quiesce(), 'initial update was not acknowledged'
    assert sim.last_delivered_price('S1') == price
    assert not sim.in_flight()


def _tick_until_ack(sim, acks_before, bound=50):
    for _ in range(bound):
        sim.tick()
        if len(sim.acks) > acks_before:
            return
    raise AssertionError('station did not acknowledge the in-flight update')


def test_desired_equal_to_confirmed_sends_nothing():
    for seed in SEEDS:
        sim = _sim(seed)
        _establish_confirmed(sim, P)
        sent_before = len(sim.sent)
        sim.set_desired_price('S1', P)
        sim.tick()
        assert sim.quiesce()
        assert len(sim.sent) == sent_before


def test_return_to_confirmed_after_other_ack_sends_confirmed_once():
    for seed in SEEDS:
        sim = _sim(seed)
        _establish_confirmed(sim, P)
        sent_base = len(sim.sent)
        sim.set_desired_price('S1', P)
        sim.tick()
        assert len(sim.sent) == sent_base
        acks_base = len(sim.acks)
        sim.set_desired_price('S1', Q)
        sim.tick()
        assert [e['price'] for e in sim.sent[sent_base:]] == [Q]
        sim.set_desired_price('S1', P)
        _tick_until_ack(sim, acks_base)
        ack_time, ack_station = sim.acks[acks_base]
        assert ack_station == 'S1'
        assert sim.quiesce()
        later = sim.sent[sent_base:]
        assert [e['price'] for e in later] == [Q, P]
        assert later[1]['time'] >= ack_time
        assert sim.displayed('S1') == P


def test_ack_of_return_price_sends_nothing_more():
    for seed in SEEDS:
        sim = _sim(seed)
        _establish_confirmed(sim, Q)
        sent_base = len(sim.sent)
        sim.set_desired_price('S1', P)
        sim.tick()
        assert [e['price'] for e in sim.sent[sent_base:]] == [P]
        acks_base = len(sim.acks)
        sim.set_desired_price('S1', Q)
        sim.tick()
        sim.set_desired_price('S1', P)
        _tick_until_ack(sim, acks_base)
        ack_time, ack_station = sim.acks[acks_base]
        assert ack_station == 'S1'
        assert sim.quiesce()
        assert [e['price'] for e in sim.sent[sent_base:]] == [P]
        assert all(e['time'] < ack_time for e in sim.sent[sent_base:])
        assert sim.displayed('S1') == P
