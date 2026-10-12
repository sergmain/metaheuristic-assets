'''GASV4E2CM-10: a desired price superseded before it is sent is never sent to the station.'''
import app
from nrvv_env import DMAX, OUTAGE_MAX, Simulation

STATION = 'S1'
OLD_PRICE = '100'
NEW_PRICE = '120'
SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)
IDLE_TICKS = 4 * OUTAGE_MAX + 2 * DMAX


def run_supersession(sim, station_id, prices):
    '''Set each price for the station in turn, all before any tick, then let the service dispatch.'''
    for price in prices:
        sim.set_desired_price(station_id, price)
    sim.tick()
    sim.quiesce(bound=2000, idle_ticks=IDLE_TICKS)


def assert_only_new_price_sent(sim, station_id, seed, superseded):
    prices = [entry['price'] for entry in sim.sent_to(station_id)]
    for price in superseded:
        assert price not in prices, f'seed {seed}: superseded price {price} sent, sends={prices}'
    assert prices, f'seed {seed}: pending price {NEW_PRICE} never sent'
    assert set(prices) == {NEW_PRICE}, f'seed {seed}: sends={prices}'


def test_superseded_price_never_sent_to_station():
    for seed in SEEDS:
        sim = Simulation(app, seed)
        run_supersession(sim, STATION, (OLD_PRICE, NEW_PRICE))
        prices = [entry['price'] for entry in sim.sent_to(STATION)]
        assert OLD_PRICE not in prices, f'seed {seed}: superseded price sent, sends={prices}'


def test_only_new_price_sent_to_station():
    for seed in SEEDS:
        sim = Simulation(app, seed)
        run_supersession(sim, STATION, (OLD_PRICE, NEW_PRICE))
        assert_only_new_price_sent(sim, STATION, seed, (OLD_PRICE,))


def test_superseded_price_not_sent_without_loss_or_outage():
    for seed in SEEDS:
        sim = Simulation(app, seed, loss=0.0, outage=0.0)
        run_supersession(sim, STATION, (OLD_PRICE, NEW_PRICE))
        assert_only_new_price_sent(sim, STATION, seed, (OLD_PRICE,))


def test_superseded_price_not_sent_under_heavy_loss_and_outages():
    for seed in SEEDS:
        sim = Simulation(app, seed, loss=0.5, outage=1.0)
        run_supersession(sim, STATION, (OLD_PRICE, NEW_PRICE))
        assert_only_new_price_sent(sim, STATION, seed, (OLD_PRICE,))


def test_every_price_superseded_in_a_chain_is_skipped():
    for seed in SEEDS:
        sim = Simulation(app, seed)
        run_supersession(sim, STATION, ('90', OLD_PRICE, '110', NEW_PRICE))
        assert_only_new_price_sent(sim, STATION, seed, ('90', OLD_PRICE, '110'))


def test_superseded_price_never_sent_to_any_station():
    for seed in SEEDS:
        sim = Simulation(app, seed)
        for station_id in sim.stations:
            sim.set_desired_price(station_id, OLD_PRICE)
            sim.set_desired_price(station_id, NEW_PRICE)
        sim.tick()
        sim.quiesce(bound=2000, idle_ticks=IDLE_TICKS)
        for station_id in sim.stations:
            assert_only_new_price_sent(sim, station_id, seed, (OLD_PRICE,))
