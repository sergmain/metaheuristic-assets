'''GASV4E2CL-35: re-setting the desired price to the price of the most recent sent update sends nothing.'''
import inspect

import app
from nrvv_env import Simulation, price_at_send_violations

PRICE = 1.459
STATION = 'S1'
SEEDS = (1, 2, 3, 4, 5)


def _new_server(send_price_update):
    for value in vars(app).values():
        if inspect.isclass(value) and value.__module__ == app.__name__ and hasattr(value, 'set_desired_price'):
            return value(send_price_update)
    app.send_price_update = send_price_update
    return app


def _new_sim(seed):
    # duration=0: no scheduled central price changes; each test drives its own changes
    return Simulation(seed, lambda send: _new_server(send), duration=0)


def _sends_to(sim, station_id):
    return [s for s in sim.sends if s.station == station_id]


def test_same_price_after_settled_send_is_not_sent():
    for seed in SEEDS:
        sim = _new_sim(seed)
        sim.server.set_desired_price(STATION, PRICE)
        sim.run_until_idle()
        sent_before = _sends_to(sim, STATION)
        assert sent_before and sent_before[-1].price == PRICE
        received_before = len(sim.stations[STATION].received)

        sim.server.set_desired_price(STATION, PRICE)
        sim.run_until_idle()

        sends = _sends_to(sim, STATION)
        assert len(sends) == len(sent_before)
        assert sends[-1].price == PRICE
        assert sim.stations[STATION].displayed_price == PRICE
        assert len(sim.stations[STATION].received) == received_before
        assert sim.desired_price(STATION) == PRICE
        assert not price_at_send_violations(sim)


def test_same_price_while_update_in_flight_is_not_sent():
    for seed in SEEDS:
        sim = _new_sim(seed)
        sim.server.set_desired_price(STATION, PRICE)
        sends_before = _sends_to(sim, STATION)
        assert len(sends_before) == 1 and sim.in_flight() >= 1

        sim.server.set_desired_price(STATION, PRICE)
        sim.run_until_idle()

        sends = _sends_to(sim, STATION)
        assert len(sends) == 1
        assert sends[-1].price == PRICE
        assert sim.stations[STATION].displayed_price == PRICE
        assert sim.desired_price(STATION) == PRICE
        assert not price_at_send_violations(sim)
