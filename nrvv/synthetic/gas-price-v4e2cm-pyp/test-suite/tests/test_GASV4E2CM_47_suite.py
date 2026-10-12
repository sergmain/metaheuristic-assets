import app
from nrvv_env import OUTAGE_MAX, Simulation

SEEDS = range(10)
SETTLE_TICKS = 300
PAST_ALL_OUTAGES = 130


def _settle(sim, ticks):
    for _ in range(ticks):
        sim.tick()


def test_last_desired_price_displayed_after_schedule_settles():
    for seed in SEEDS:
        sim = Simulation(app, seed)
        sim.run_schedule(100)
        _settle(sim, PAST_ALL_OUTAGES)
        final = {station_id: 1000 + index for index, station_id in enumerate(sim.stations)}
        for station_id, price in final.items():
            sim.set_desired_price(station_id, price)
        _settle(sim, SETTLE_TICKS)
        for station_id, price in final.items():
            assert sim.displayed(station_id) == price, f'seed={seed} station={station_id}'


def test_station_in_outage_at_last_set_still_converges():
    for seed in SEEDS:
        sim = Simulation(app, seed)
        sim.run_schedule(60)
        _settle(sim, PAST_ALL_OUTAGES)
        target = 'S1'
        sim.stations[target].outages.append((sim.now, sim.now + OUTAGE_MAX))
        final = 2000
        sim.set_desired_price(target, final)
        _settle(sim, SETTLE_TICKS)
        assert sim.displayed(target) == final, f'seed={seed}'


def test_last_desired_price_displayed_without_faults():
    for seed in SEEDS:
        sim = Simulation(app, seed, loss=0.0, outage=0.0)
        sim.run_schedule(100)
        _settle(sim, PAST_ALL_OUTAGES)
        final = {station_id: 3000 + index for index, station_id in enumerate(sim.stations)}
        for station_id, price in final.items():
            sim.set_desired_price(station_id, price)
        _settle(sim, SETTLE_TICKS)
        for station_id, price in final.items():
            assert sim.displayed(station_id) == price, f'seed={seed} station={station_id}'
