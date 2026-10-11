"""GASV4ACCJ-6: a station left on an older price by out-of-order delivery ends on the newest price.

Driven only through nrvv_env: the seeded Simulation creates the stations, delivers the
updates (in an order that can invert send order) and reports ground truth. The app module
is reloaded before each run so that no state carries over between seeds.
"""

import importlib

import app
from nrvv_env import Simulation

HORIZON = 1800.0
SEEDS = range(60)


def _run(seed):
    module = importlib.reload(app)
    sim = Simulation(seed, horizon=HORIZON)
    sim.connect(module)
    sim.run_until(HORIZON + 600.0)
    sim.run_until_quiet()
    return sim


def _late_older_deliveries(sim):
    """Pairs (newer, late): an update sent later was delivered first, then an older one arrived."""
    delivered = sim.deliveries()
    pairs = []
    for position, late in enumerate(delivered):
        for early in delivered[:position]:
            if (early.station == late.station
                    and early.index > late.index
                    and early.price != late.price):
                pairs.append((early, late))
                break
    return pairs


def _cases():
    cases = []
    for seed in SEEDS:
        sim = _run(seed)
        for newer, late in _late_older_deliveries(sim):
            station = late.station
            newest = sim.desired_price(station)
            if newest == late.price:
                continue
            cases.append((seed, sim, station, newer, late, newest))
    return cases


def test_station_applies_newest_price_after_late_older_update():
    cases = _cases()
    assert cases, "no seed produced a newer update delivered before an older one"
    for seed, sim, station, newer, late, newest in cases:
        applied = sim.applied_price(station)
        assert applied == newest, f"seed {seed} {station}: applying {applied}, newest is {newest}"
        assert applied != late.price, f"seed {seed} {station}: still on stale price {late.price}"


def test_newest_price_reapplied_after_late_older_update_without_new_change():
    cases = _cases()
    assert cases, "no seed produced a newer update delivered before an older one"
    for seed, sim, station, newer, late, newest in cases:
        history = sim.applied_history(station)
        last_time, last_price = history[-1]
        assert last_price == newest, f"seed {seed} {station}: last applied {last_price}, newest {newest}"
        assert last_time >= late.delivered_at, f"seed {seed} {station}: newest not applied after late update"
        status = sim.status(station)
        assert status is not None, f"seed {seed} {station}: status query returned nothing"
