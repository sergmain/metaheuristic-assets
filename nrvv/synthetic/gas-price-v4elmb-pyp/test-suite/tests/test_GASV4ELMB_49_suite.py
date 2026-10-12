# GASV4ELMB-7: the station displays the price carried by the last update it received.
from nrvv_env import Simulation

import app

STATION = 'S0'
FIRST_PRICE = 1.50
SECOND_PRICE = 1.75
SEEDS = (1, 2, 3, 5, 8)
MAX_TICKS = 2000


def _single_station_run(seed):
    sim = Simulation(app, seed, stations=[STATION])
    sim._script_by_tick = {}
    sim.outages = {STATION: []}
    return sim


def _wait_until_displayed(sim, price):
    while sim.stations[STATION].price != price:
        if sim.tick >= MAX_TICKS:
            raise AssertionError('station still shows %r after %d ticks (seed %r)' % (sim.stations[STATION].price, sim.tick, sim.seed))
        sim.step()


def test_station_displays_first_price_after_first_update():
    for seed in SEEDS:
        sim = _single_station_run(seed)
        sim._central_change(sim.tick, STATION, FIRST_PRICE)
        _wait_until_displayed(sim, FIRST_PRICE)
        assert sim.stations[STATION].price == 1.50
        assert sim.server_state(STATION)['desired_price'] == 1.50


def test_station_displays_latest_price_after_second_update():
    for seed in SEEDS:
        sim = _single_station_run(seed)
        sim._central_change(sim.tick, STATION, FIRST_PRICE)
        _wait_until_displayed(sim, FIRST_PRICE)
        sim._central_change(sim.tick, STATION, SECOND_PRICE)
        _wait_until_displayed(sim, SECOND_PRICE)
        shown = sim.stations[STATION].price
        assert shown == 1.75
        assert shown != 1.50
        assert sim.server_state(STATION)['desired_price'] == 1.75
