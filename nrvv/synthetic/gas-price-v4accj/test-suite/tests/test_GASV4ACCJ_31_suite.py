'''Tests for GASV4ACCJ-31 / GASV4ACCJ-18: the station receives only the bare price value.

Every price update the server sends is captured by the simulated transport
(Simulation.sends) and delivered to the station (Station.deliveries). Each
captured message must carry the price value and nothing else.
'''

import app
from nrvv_env import Simulation

SEEDS = (1, 7, 42)


def _run(seed):
    sim = Simulation(seed, app)
    sim.run_until_idle()
    return sim


def _desired_prices(sim, station_id):
    return {change.price for change in sim.changes if change.station_id == station_id}


def test_every_captured_update_message_is_a_bare_int_price():
    captured = 0
    for seed in SEEDS:
        sim = _run(seed)
        for send in sim.sends:
            captured += 1
            assert type(send.price) is int, (seed, send)
    assert captured > 0


def test_captured_update_price_is_a_desired_price_of_that_station():
    for seed in SEEDS:
        sim = _run(seed)
        for send in sim.sends:
            assert send.price in _desired_prices(sim, send.station_id), (seed, send)


def test_delivered_station_message_carries_only_the_price_value():
    delivered = 0
    for seed in SEEDS:
        sim = _run(seed)
        for station_id, station in sim.stations.items():
            for delivery in station.deliveries:
                delivered += 1
                assert type(delivery.price) is int, (seed, station_id, delivery)
                assert delivery.price in _desired_prices(sim, station_id), (seed, delivery)
    assert delivered > 0


def test_update_message_price_is_not_a_container_or_text_wrapping_extra_fields():
    for seed in SEEDS:
        sim = _run(seed)
        for send in sim.sends:
            assert not isinstance(send.price, (tuple, list, dict, set, str, bytes)), (seed, send)
            assert not isinstance(send.price, bool), (seed, send)
