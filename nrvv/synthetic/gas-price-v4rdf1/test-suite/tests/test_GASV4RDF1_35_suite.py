import app
from nrvv_env import Simulation

MAX_STEPS = 20000
SEEDS = (0, 1, 2, 3, 4)


def _sent_after(sim, station, step):
    return [u for u in sim.sent_log if u.station == station and u.step > step]


def test_price_change_sends_update_with_new_price():
    for seed in SEEDS:
        station = 'one-%d' % seed
        sim = Simulation(app, seed, stations=(station,),
                         script=[(station, 100), (station, 200)])
        sim.run(MAX_STEPS)
        assert len(sim.call_log) == 2
        change = sim.call_log[1]
        assert change.price == 200
        after = _sent_after(sim, station, change.step)
        assert any(u.price == 200 for u in after), (seed, sim.sent_log)
        assert all(u.price == 200 for u in after), (seed, after)


def test_further_price_change_sends_update_with_newest_price():
    for seed in SEEDS:
        station = 'two-%d' % seed
        sim = Simulation(app, seed, stations=(station,),
                         script=[(station, 100), (station, 200), (station, 300)])
        sim.run(MAX_STEPS)
        assert len(sim.call_log) == 3
        third = sim.call_log[2]
        assert third.price == 300
        after = _sent_after(sim, station, third.step)
        assert any(u.price == 300 for u in after), (seed, sim.sent_log)
        assert all(u.price == 300 for u in after), (seed, after)


def test_last_desired_price_change_is_sent_to_each_station_random_runs():
    for seed in SEEDS:
        names = ('r%d-a' % seed, 'r%d-b' % seed)
        sim = Simulation(app, seed, stations=names, calls=12, prices=(1, 50))
        sim.run(MAX_STEPS)
        for name in names:
            calls = [c for c in sim.call_log if c.station == name]
            if not calls:
                continue
            changes = [c for i, c in enumerate(calls)
                       if i == 0 or calls[i - 1].price != c.price]
            last_change = changes[-1]
            final_price = calls[-1].price
            after = _sent_after(sim, name, last_change.step)
            assert any(u.price == last_change.price for u in after), (seed, name, sim.sent_log)
            assert all(u.price == final_price for u in after), (seed, name, after)
