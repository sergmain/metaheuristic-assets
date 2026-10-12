'''Requirement GASV4E2CM-14 (dispatch rule), test case GASV4E2CM-35.'''
import app
from nrvv_env import DMAX, Simulation

SEEDS = (1, 2, 3, 4, 5)


def _fields(obj):
    if isinstance(obj, dict):
        return {str(name).lower(): value for name, value in obj.items()}
    return {
        name.lower(): getattr(obj, name)
        for name in dir(obj)
        if not name.startswith('_') and not callable(getattr(obj, name))
    }


def _pick(status, include, exclude=()):
    matches = [
        value
        for name, value in _fields(status).items()
        if all(word in name for word in include) and not any(word in name for word in exclude)
    ]
    assert len(matches) == 1, f'expected one status field matching {include}, found {len(matches)}'
    return matches[0]


def test_price_change_sends_one_update_with_new_price_and_records_it_in_flight():
    for seed in SEEDS:
        sim = Simulation(app, seed, stations=('S1',), loss=0.0, outage=0.0)
        sim.set_desired_price('S1', 10.0)
        assert sim.quiesce()
        assert _pick(sim.status('S1'), ('confirm', 'price')) == 10.0
        before = len(sim.sent_to('S1'))
        sim.set_desired_price('S1', 12.5)
        new = sim.sent_to('S1')[before:]
        assert len(new) == 1, f'seed {seed}: expected exactly one update, got {len(new)}'
        assert new[0]['price'] == 12.5
        status = sim.status('S1')
        assert _pick(status, ('flight', 'price')) == 12.5
        assert _pick(status, ('flight',), ('price',)) == sim.now
        assert _pick(status, ('confirm', 'price')) == 10.0


def test_no_second_update_while_first_is_unacknowledged():
    for seed in SEEDS:
        sim = Simulation(app, seed, stations=('S1',), loss=0.0, outage=0.0)
        sim.set_desired_price('S1', 10.0)
        assert sim.quiesce()
        sends_base = len(sim.sent_to('S1'))
        acks_base = sim.acks_per_station()['S1']
        sim.set_desired_price('S1', 12.5)
        assert len(sim.sent_to('S1')) == sends_base + 1, f'seed {seed}: update not sent at once'
        sim.set_desired_price('S1', 13.0)
        for _ in range(6 * DMAX):
            if sim.acks_per_station()['S1'] > acks_base:
                break
            sim.tick()
            if sim.acks_per_station()['S1'] == acks_base:
                assert len(sim.sent_to('S1')) == sends_base + 1, f'seed {seed}: second update sent while first unacknowledged'
        assert sim.acks_per_station()['S1'] > acks_base, f'seed {seed}: first update was never acknowledged'
