import app
from nrvv_env import Simulation

STATION = 'S0'
P1, P1_LATER, P2 = 3, 7, 11
SEEDS = (1, 2, 3, 4)


def _quiet_sim(seed):
    sim = Simulation(app, seed, stations=[STATION])
    sim._script_by_tick = {}
    return sim


def _set_desired(sim, price):
    sim._central_change(sim.tick, STATION, price)


def test_set_desired_price_on_fresh_station_sets_desired_and_counter_one():
    for seed in SEEDS:
        sim = _quiet_sim(seed)
        _set_desired(sim, P1)
        view = sim.server_state(STATION)
        assert view['desired_price'] == P1
        assert view['shown_price'] is None
        sim.run()
        assert sim.sends, 'no update was sent for the first desired price'
        assert sim.sends[0].seq == 1
        assert sim.sends[0].price == P1


def test_set_desired_price_while_in_flight_and_pending_leaves_record_unchanged():
    for seed in SEEDS:
        sim = _quiet_sim(seed)
        _set_desired(sim, P1)
        for _ in range(5):
            if sim.server_state(STATION)['in_flight_seq'] is not None:
                break
            sim.step()
        assert sim.server_state(STATION)['in_flight_seq'] is not None
        _set_desired(sim, P1_LATER)
        before = sim.server_state(STATION)
        assert before['pending']
        _set_desired(sim, P2)
        after = sim.server_state(STATION)
        assert after['desired_price'] == P2
        for field in ('in_flight_seq', 'in_flight_price', 'pending', 'shown_price'):
            assert after[field] == before[field], field
        sends_before = len(sim.sends)
        sim.run()
        fresh = [s for s in sim.sends[sends_before:] if not s.retransmission]
        if fresh:
            assert fresh[0].seq == before['in_flight_seq'] + 1
