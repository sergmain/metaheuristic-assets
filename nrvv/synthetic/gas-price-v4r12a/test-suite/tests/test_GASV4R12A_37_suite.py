'''Suite for GASV4R12A-9: a price superseded before its update is sent is never sent.'''
import app
from nrvv_env import Simulation

PRICE_A = 100
PRICE_B = 250
PRICE_C = 50
SEEDS = (1, 2, 3, 4, 5)


def _make_sim(seed):
    sim = Simulation(seed, stations=('s1',), stop_tick=1, fault_window=(0, 0),
                     loss=0.0, change_rate=0.0)
    sim.attach(lambda send: app.Server(send_update=send))
    return sim


def _station_sends(sim):
    return [s for s in sim.sends if s.station == 's1']


def test_same_tick_superseded_price_is_never_sent():
    for seed in SEEDS:
        sim = _make_sim(seed)
        sim.source_schedule = {1: [('s1', PRICE_A), ('s1', PRICE_B)]}
        sim.assert_converged()
        assert [c.price for c in sim.changes] == [PRICE_A, PRICE_B]
        sends = _station_sends(sim)
        assert all(s.price != PRICE_A for s in sends), seed
        assert any(s.price == PRICE_B for s in sends), seed
        assert sim.stations['s1'].displayed == PRICE_B, seed


def test_price_superseded_while_earlier_update_unacked_is_never_sent():
    for seed in SEEDS:
        sim = _make_sim(seed)
        sim.source_schedule = {1: [('s1', PRICE_C)], 2: [('s1', PRICE_A), ('s1', PRICE_B)]}
        sim.set_reachable('s1', False)
        sim.run(1)
        sim.step()
        sim.set_reachable('s1', None)
        sim.assert_converged()
        assert [c.price for c in sim.changes] == [PRICE_C, PRICE_A, PRICE_B]
        sends = _station_sends(sim)
        assert all(s.price != PRICE_A for s in sends), seed
        assert any(s.price == PRICE_B for s in sends), seed
        assert sim.stations['s1'].displayed == PRICE_B, seed
