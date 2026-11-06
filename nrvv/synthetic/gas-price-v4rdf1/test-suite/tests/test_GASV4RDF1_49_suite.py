import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 5, 8)
PRICES = (1, 250, 1000)
MAX_STEPS = 10000


def _settle(seed, station, price):
    sim = Simulation(app, seed, stations=(station, 'other'), script=[(station, price)])
    sim.run(max_steps=MAX_STEPS)
    assert sim.is_quiet()
    assert sim.last_ack_price(station) == price
    return sim


def _updates_to(sim, station):
    return [u for u in sim.sent_log if u.station == station]


def test_no_update_sent_when_station_already_on_latest_price():
    for seed in SEEDS:
        for price in PRICES:
            station = 'st-%d-%d' % (seed, price)
            _settle(seed, station, price)
            trigger = Simulation(app, seed + 1000, stations=(station, 'other'), script=[(station, price)])
            trigger.run(max_steps=MAX_STEPS)
            assert trigger.is_quiet()
            assert len(trigger.call_log) == 1
            assert len(_updates_to(trigger, station)) == 0


def test_repeated_trigger_at_same_price_sends_no_update():
    for seed in SEEDS:
        price = PRICES[seed % len(PRICES)]
        station = 'rep-%d' % seed
        _settle(seed, station, price)
        trigger = Simulation(app, seed + 2000, stations=(station, 'other'), script=[(station, price)] * 3)
        trigger.run(max_steps=MAX_STEPS)
        assert trigger.is_quiet()
        assert len(trigger.call_log) == 3
        assert len(_updates_to(trigger, station)) == 0
