import inspect

import app
from nrvv_env import Simulation

STATION = 'S1'
OTHER = 'S2'
SEEDS = range(20)


def _make_service(sim):
    classes = [obj for obj in vars(app).values()
               if inspect.isclass(obj) and callable(getattr(obj, 'set_desired_price', None))]
    assert classes, 'app must provide a class with set_desired_price'
    return sim.connect(classes[0](sim.send_price_update))


def _run_superseded(seed, intermediates, newest):
    # The station has an update in flight (price 1) when the intermediate desired
    # prices and then the newest one are set, so none of them can be sent before
    # the in-flight slot clears.
    sim = Simulation(seed, [STATION, OTHER], changes=0,
                     max_update_delay=1 + seed % 4, max_ack_delay=1 + seed % 3)
    _make_service(sim)
    sim.issue_desired_price(STATION, 1)
    assert [s.price for s in sim.sends if s.station == STATION] == [1]
    for price in intermediates:
        sim.issue_desired_price(STATION, price)
    sim.issue_desired_price(STATION, newest)
    sim.run()
    return sim


def test_superseded_price_is_never_sent():
    for seed in SEEDS:
        sim = _run_superseded(seed, [2], 3)
        sent = [s.price for s in sim.sends if s.station == STATION]
        assert 2 not in sent, f'seed {seed}: superseded price sent, sends={sent}'


def test_newer_price_is_the_one_sent_after_in_flight_clears():
    for seed in SEEDS:
        sim = _run_superseded(seed, [2], 3)
        sent = [s.price for s in sim.sends if s.station == STATION]
        assert sent == [1, 3], f'seed {seed}: sends={sent}'
        assert sim.displayed(STATION) == 3, f'seed {seed}: displayed={sim.displayed(STATION)}'


def test_chain_of_superseded_prices_is_never_sent():
    for seed in SEEDS:
        sim = _run_superseded(seed, [2, 4, 5], 3)
        sent = [s.price for s in sim.sends if s.station == STATION]
        assert sent == [1, 3], f'seed {seed}: sends={sent}'
