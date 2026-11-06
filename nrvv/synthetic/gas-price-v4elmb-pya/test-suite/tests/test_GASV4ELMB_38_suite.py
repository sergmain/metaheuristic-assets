import random

import app
from nrvv_env import Simulation, default_view

SEEDS = (1, 2, 3)
STATION = 'station-0'
PRICE_MAX = 20


def _acknowledged(view, seq):
    # Acknowledgements are cumulative: the only update still in flight is the in-flight one,
    # so an update below it is acknowledged, and an update at or above it is not.
    in_flight = view['in_flight_seq']
    return in_flight is None or in_flight > seq


def _acknowledged_states(sim):
    view = default_view(sim.query(STATION))
    return [_acknowledged(view, seq) for seq in (1, 2, 3)]


def test_cumulative_ack_marks_updates_up_to_sequence():
    for seed in SEEDS:
        sim = Simulation(seed, lambda send: app.Service(send))
        prices = random.Random(seed).sample(range(PRICE_MAX + 1), 3)
        for price in prices:
            sim.service.set_desired_price(STATION, price)
        sent = [(s.station, s.seq, s.price) for s in sim.sends]
        assert sent == [(STATION, 1, prices[0]), (STATION, 2, prices[1]), (STATION, 3, prices[2])], sent

        sim.service.ack_received(STATION, 2)
        assert _acknowledged_states(sim) == [True, True, False], seed

        sim.service.ack_received(STATION, 2)
        assert _acknowledged_states(sim) == [True, True, False], seed

        sim.service.ack_received(STATION, 3)
        assert _acknowledged_states(sim) == [True, True, True], seed
