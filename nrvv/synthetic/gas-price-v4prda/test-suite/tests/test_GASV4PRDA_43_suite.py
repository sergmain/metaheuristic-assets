"""Acceptance tests for GASV4PRDA-43 (requirement GASV4PRDA-9).

A station that is not modified shows the price carried by the last update it
received. The service sends two price updates for the same station in
sequence, P1 then P2; once the second one has been received the station must
show exactly P2, without any change to the station.
"""

import random

import app
from nrvv_env import Simulation

PRICES = (10, 20, 30, 40, 50)
SEEDS = (1, 2, 3, 4, 5)


def _two_prices(seed):
    rng = random.Random(f"GASV4PRDA-43/{seed}")
    first, second = rng.sample(PRICES, 2)
    return first, second


def _simulation(seed, station_id, **overrides):
    # The server module keeps its state between simulations, so every test
    # uses its own station identifiers.
    options = dict(
        stations=[station_id],
        change_rate=0.0,
        loss_rate=0.0,
        duplicate_rate=0.0,
        outages=False,
    )
    options.update(overrides)
    return Simulation(seed, server=app, **options)


def _run_until(sim, condition, limit):
    for _ in range(limit):
        if condition():
            return True
        sim.step()
    return condition()


def test_second_update_leaves_unmodified_station_showing_second_price():
    for seed in SEEDS:
        first, second = _two_prices(seed)
        station_id = f"GASV43-seq-{seed}"
        sim = _simulation(seed, station_id)
        station = sim.stations[station_id]

        app.desired_price_change(station_id, first)
        assert _run_until(sim, lambda: station.display == first, 60), f"seed {seed}: first price never shown"

        app.desired_price_change(station_id, second)
        sim.run(60)

        assert station.display == second, f"seed {seed}"
        assert station.display_at(sim.now) == second, f"seed {seed}"
        assert station.received[-1][2] == second, f"seed {seed}"
        assert [price for _, price in station.display_history] == [first, second], f"seed {seed}"
        assert sim.send_calls[-1].price == second, f"seed {seed}"


def test_updates_issued_together_leave_station_showing_second_price():
    for seed in SEEDS:
        first, second = _two_prices(seed)
        station_id = f"GASV43-together-{seed}"
        sim = _simulation(seed, station_id)
        station = sim.stations[station_id]

        app.desired_price_change(station_id, first)
        app.desired_price_change(station_id, second)
        sim.run(60)

        assert station.display == second, f"seed {seed}"
        assert station.received[-1][2] == second, f"seed {seed}"
        assert sim.send_calls[-1].price == second, f"seed {seed}"


def test_last_update_wins_when_transport_loses_messages_and_stations_go_offline():
    for seed in SEEDS:
        first, second = _two_prices(seed)
        station_id = f"GASV43-lossy-{seed}"
        sim = _simulation(seed, station_id, loss_rate=0.3, outages=True)
        station = sim.stations[station_id]

        app.desired_price_change(station_id, first)
        sim.run(10)
        app.desired_price_change(station_id, second)
        sim.run(400)

        assert station.display == second, f"seed {seed}"
        assert station.display_at(sim.now) == second, f"seed {seed}"
        assert station.received[-1][2] == second, f"seed {seed}"
