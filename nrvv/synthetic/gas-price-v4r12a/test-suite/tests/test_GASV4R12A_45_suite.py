import app
from nrvv_env import Simulation

STATION = 's1'
SEEDS = (1, 2, 3, 4, 5)


def _make_sim(seed, schedule, stop_tick):
    sim = Simulation(seed, stations=(STATION,), stop_tick=stop_tick,
                     fault_window=(0, 0), loss=0.0)
    sim.source_schedule = schedule
    sim.attach(lambda send: app.Server(send_update=send))
    return sim


def _step_until_sent(sim, max_steps=10):
    for _ in range(max_steps):
        sim.step()
        if sim.sends:
            break
    return sim.sends


def test_newer_price_replaces_unsent_price_before_handover():
    for seed in SEEDS:
        price_a, price_b = 100 + seed, 500 + seed
        sim = _make_sim(seed, {1: [(STATION, price_a), (STATION, price_b)]}, stop_tick=1)
        sends = _step_until_sent(sim)
        assert len(sends) == 1, 'expected exactly one update, got {}'.format(sends)
        version_a = sim.changes[0].result
        version_b = sim.changes[1].result
        assert version_a != version_b
        assert sends[0].station == STATION
        assert sends[0].price == price_b
        assert sends[0].version == version_b
        sim.run(30)
        assert all(s.price != price_a for s in sim.sends)
        assert all(s.price == price_b and s.version == version_b for s in sim.sends)
        assert sim.stations[STATION].displayed == price_b


def test_single_accepted_price_is_carried_with_its_version():
    for seed in SEEDS:
        price_a = 100 + seed
        sim = _make_sim(seed, {1: [(STATION, price_a)]}, stop_tick=1)
        sends = _step_until_sent(sim)
        assert sends, 'no update was handed over'
        version_a = sim.changes[0].result
        for s in sends:
            assert s.station == STATION
            assert s.price == price_a
            assert s.version == version_a
        sim.run(30)
        for s in sim.sends:
            assert s.price == price_a
            assert s.version == version_a
        assert sim.stations[STATION].displayed == price_a
