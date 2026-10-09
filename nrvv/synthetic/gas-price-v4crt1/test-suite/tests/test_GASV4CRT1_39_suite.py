import inspect
import random

import app
from nrvv_env import Simulation

STATION = 'station-1'
PRICES = (1, 2, 3, 4, 5)
SEEDS = range(25)


def _build_service(port):
    classes = [obj for obj in vars(app).values()
               if inspect.isclass(obj) and obj.__module__ == app.__name__
               and callable(getattr(obj, 'set_desired_price', None))]
    assert classes, 'app must define a class offering set_desired_price'
    cls = classes[0]
    for name in inspect.signature(cls).parameters:
        if any(word in name.lower() for word in ('port', 'send', 'outbound')):
            return cls(**{name: port})
    return cls(port)


def _new_run(seed, max_update_delay, max_ack_delay):
    sim = Simulation(seed, [STATION], changes=0,
                     max_update_delay=max_update_delay, max_ack_delay=max_ack_delay)
    sim.connect(_build_service(sim.send_price_update))
    return sim


def _two_prices(seed):
    first, second = random.Random(seed).sample(PRICES, 2)
    return first, second


def _drive(sim, order, first, second):
    # first_then_second: the first update is delivered and acknowledged before the second is issued.
    # second_while_first_in_flight: the second desired price is issued while the first is still unacknowledged.
    if order == 'first_then_second':
        sim.issue_desired_price(STATION, first)
        sim.run()
        sim.issue_desired_price(STATION, second)
    else:
        sim.issue_desired_price(STATION, first)
        sim.issue_desired_price(STATION, second)
    sim.run()


def _assert_latest_displayed(order, max_update_delay, max_ack_delay):
    for seed in SEEDS:
        first, second = _two_prices(seed)
        sim = _new_run(seed, max_update_delay, max_ack_delay)
        _drive(sim, order, first, second)
        displayed = sim.displayed(STATION)
        assert displayed == second, (
            f'seed {seed}, {order}: station displays {displayed!r}, '
            f'latest desired price is {second!r}')


def test_latest_price_displayed_first_then_second_short_delays():
    _assert_latest_displayed('first_then_second', 4, 4)


def test_latest_price_displayed_first_then_second_long_delays():
    _assert_latest_displayed('first_then_second', 8, 8)


def test_latest_price_displayed_second_while_first_in_flight_short_delays():
    _assert_latest_displayed('second_while_first_in_flight', 4, 4)


def test_latest_price_displayed_second_while_first_in_flight_long_delays():
    _assert_latest_displayed('second_while_first_in_flight', 8, 8)
