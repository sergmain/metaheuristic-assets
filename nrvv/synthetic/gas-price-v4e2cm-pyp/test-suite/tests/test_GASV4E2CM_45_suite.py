import random

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)
PRICE_A = 10
PRICE_B = 20
ACK_WAIT_MAX = 60


def _stations(tag, count):
    return tuple(f'{tag}-{index}' for index in range(count))


def _assert_at_most_one_outstanding(sim):
    sends = sim.sends_per_station()
    acks = sim.acks_per_station()
    for station_id in sim.stations:
        assert sends[station_id] - acks[station_id] <= 1, f'two updates outstanding to {station_id}'


def test_second_update_waits_for_first_acknowledgement():
    for seed in SEEDS:
        sim = Simulation(app, seed, stations=_stations(f'wait{seed}', 1), loss=0.0, outage=0.0)
        (station_id,) = sim.stations
        sim.set_desired_price(station_id, PRICE_A)
        assert [entry['price'] for entry in sim.sent_to(station_id)] == [PRICE_A]
        sim.set_desired_price(station_id, PRICE_B)
        assert [entry['price'] for entry in sim.sent_to(station_id)] == [PRICE_A], 'B dispatched while A unacknowledged'

        while sim.acks_per_station()[station_id] == 0 and sim.now < ACK_WAIT_MAX:
            sim.tick()
            if sim.acks_per_station()[station_id] == 0:
                assert len(sim.sent_to(station_id)) == 1, 'B dispatched before A was acknowledged'
        assert sim.acks_per_station()[station_id] == 1, 'A was never acknowledged'

        assert len(sim.sent_to(station_id)) == 2, 'B not dispatched after A was acknowledged'
        assert sim.sent_to(station_id)[1]['time'] >= sim.acks[0][0]

        assert sim.quiesce(), 'simulation did not settle'
        assert [entry['price'] for entry in sim.sent_to(station_id)] == [PRICE_A, PRICE_B]
        assert sim.last_delivered_price(station_id) == PRICE_B
        assert sim.displayed(station_id) == PRICE_B


def test_random_bursts_never_leave_two_updates_outstanding():
    for seed in SEEDS:
        stations = _stations(f'burst{seed}', 3)
        sim = Simulation(app, seed, stations=stations, loss=0.0, outage=0.0)
        rng = random.Random(seed * 7919)
        for _ in range(150):
            if rng.random() < 0.3:
                for _ in range(rng.randint(1, 4)):
                    sim.set_desired_price(rng.choice(stations), rng.randint(1, 99))
                    _assert_at_most_one_outstanding(sim)
            sim.tick()
            _assert_at_most_one_outstanding(sim)
        assert sim.quiesce(), 'simulation did not settle'
        _assert_at_most_one_outstanding(sim)
        for station_id in stations:
            sent = sim.sent_to(station_id)
            if not sent:
                continue
            assert sim.acks_per_station()[station_id] == len(sent)
            assert sim.last_delivered_price(station_id) == sent[-1]['price']
            desired = [price for _, sid, price in sim.desired_history if sid == station_id]
            assert sent[-1]['price'] == desired[-1]


def test_outstanding_update_does_not_block_other_stations():
    sim = Simulation(app, 11, stations=_stations('indep', 2), loss=0.0, outage=0.0)
    first, second = sim.stations
    sim.set_desired_price(first, PRICE_A)
    sim.set_desired_price(second, PRICE_B)
    assert len(sim.sent_to(first)) == 1
    assert len(sim.sent_to(second)) == 1
    assert sim.quiesce(), 'simulation did not settle'
    assert sim.last_delivered_price(first) == PRICE_A
    assert sim.last_delivered_price(second) == PRICE_B
