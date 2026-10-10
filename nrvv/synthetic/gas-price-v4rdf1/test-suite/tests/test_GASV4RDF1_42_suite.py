'''Tests for GASV4RDF1-5: each station ends on the latest desired price.'''

import app
from nrvv_env import Simulation

SEEDS = range(40)
MAX_STEPS = 10000


def _run_to_quiet(sim):
    sim.run(max_steps=MAX_STEPS)
    assert sim.is_quiet(), 'no quiescence within %d steps' % MAX_STEPS
    assert sim.in_flight() == []
    assert sim.pending_acks() == 0


def test_older_price_delivered_last_leaves_latest_displayed():
    # P1 is submitted, then P2, which is the latest desired price; updates may arrive out of order
    for seed in SEEDS:
        sim = Simulation(app, seed, stations=('S1',), script=[('S1', 'P1'), ('S1', 'P2')])
        _run_to_quiet(sim)
        assert sim.desired['S1'] == 'P2'
        assert sim.displayed('S1') == 'P2', 'seed %d displays %r' % (seed, sim.displayed('S1'))


def test_resubmitted_older_price_does_not_override_latest():
    # P2, then P1, then P2 again: the latest desired price is P2
    script = [('S1', 'P2'), ('S1', 'P1'), ('S1', 'P2')]
    for seed in SEEDS:
        sim = Simulation(app, seed, stations=('S1',), script=script)
        _run_to_quiet(sim)
        assert sim.desired['S1'] == 'P2'
        assert sim.displayed('S1') == 'P2', 'seed %d displays %r' % (seed, sim.displayed('S1'))


def test_each_station_ends_on_its_own_latest_price():
    script = [('S1', 'P1'), ('S2', 'P1'), ('S1', 'P2'), ('S2', 'P2'), ('S1', 'P3'), ('S2', 'P1')]
    expected = {'S1': 'P3', 'S2': 'P1'}
    for seed in SEEDS:
        sim = Simulation(app, seed, stations=('S1', 'S2'), script=script)
        _run_to_quiet(sim)
        for name, price in expected.items():
            assert sim.desired[name] == price
            assert sim.displayed(name) == price, 'seed %d station %s displays %r' % (
                seed, name, sim.displayed(name))


def test_random_call_sequences_end_on_latest_desired_price():
    for seed in SEEDS:
        sim = Simulation(app, seed, stations=('S1', 'S2'), calls=12)
        _run_to_quiet(sim)
        for name in ('S1', 'S2'):
            if name in sim.desired:
                assert sim.displayed(name) == sim.desired[name], 'seed %d station %s' % (seed, name)


def test_many_stations_many_calls_end_on_latest_desired_price():
    names = ('S1', 'S2', 'S3', 'S4')
    for seed in range(15):
        sim = Simulation(app, seed, stations=names, calls=60, prices=(1, 5))
        _run_to_quiet(sim)
        for name in names:
            if name in sim.desired:
                assert sim.displayed(name) == sim.desired[name], 'seed %d station %s' % (seed, name)
