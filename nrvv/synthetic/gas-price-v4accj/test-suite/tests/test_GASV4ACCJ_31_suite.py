# Criterion GASV4ACCJ-31 (requirement GASV4ACCJ-18): the station receives the bare price value only.
import importlib

import app
from nrvv_env import Simulation
from nrvv_env.simulation import PRICE_HIGH, PRICE_LOW

SEEDS = (1, 2, 3, 4, 5)


def _run(seed):
    module = importlib.reload(app)
    sim = Simulation(seed)
    sim.connect(module)
    sim.run_until_quiet()
    return sim


def test_every_delivered_message_is_bare_price_int():
    for seed in SEEDS:
        sim = _run(seed)
        deliveries = sim.deliveries()
        assert deliveries, f'seed {seed}: no update reached a station'
        for record in deliveries:
            assert type(record.price) is int, (
                f'seed {seed}: message {record.index} carries {record.price!r}, not a bare price')
            assert PRICE_LOW <= record.price <= PRICE_HIGH


def test_station_holds_only_bare_price_values_it_was_sent():
    for seed in SEEDS:
        sim = _run(seed)
        scheduled = {s: set() for s in sim.stations}
        for _, station, price in sim.schedule():
            scheduled[station].add(price)
        for station in sim.stations:
            history = sim.applied_history(station)
            delivered = [r.price for r in sim.deliveries() if r.station == station]
            assert [value for _, value in history] == delivered, (
                f'seed {seed}: {station} applied values differ from the messages it received')
            for when, value in history:
                assert type(value) is int, (
                    f'seed {seed}: {station} applied {value!r} at {when}, not a bare price')
                assert value in scheduled[station], (
                    f'seed {seed}: {station} applied {value!r}, which was never a price for it')


def test_every_send_passes_a_bare_price_value():
    for seed in SEEDS:
        sim = _run(seed)
        assert sim.sends(), f'seed {seed}: the trigger produced no send'
        for record in sim.sends():
            assert type(record.price) is int, (
                f'seed {seed}: send {record.index} passed {record.price!r} as the price')
