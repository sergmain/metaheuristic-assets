'''GASV4ELMA-8: once no new desired price arrives, a reachable station displays the latest desired price within 10 minutes.'''
import app
from nrvv_env import Simulation, check

TARGET_PRICE = 1.859
SEND_TIME = 31.0  # T: after the generated price calls (stop_time=30)
BOUND = 10.0      # convergence bound in minutes
SEEDS = (1, 2, 3, 7, 11)
_PRICE_SOURCE = 1  # event priority of price-source calls in nrvv_env.sim


def _server(dispatch):
    return app.Server(dispatch_update=dispatch)


def _simulation(seed, stations=3):
    return Simulation(seed=seed, server_factory=_server, stations=stations, stop_time=30.0)


def _send_series(sim, station_id, updates):
    """Send desired prices for station_id as (time, price) pairs, in time order, as the price source would."""
    for time, price in updates:
        sim.price_schedule.append((time, station_id, price))
        sim._push(time, _PRICE_SOURCE, ('set', station_id, price))


def _displayed_at(sim, station_id, time):
    shown = None
    for r in sim.trace:
        if r.kind == 'display' and r.station == station_id and r.time <= time:
            shown = r.price
    return shown


def test_reachable_station_shows_last_price_within_10_minutes():
    for seed in SEEDS:
        sim = _simulation(seed)
        for sid in sim.station_ids:
            sim.force_reachable(sid, 0.0)
        target = sim.station_ids[0]
        _send_series(sim, target, ((30.5, 100), (30.8, 120), (SEND_TIME, TARGET_PRICE)))
        deadline = SEND_TIME + BOUND
        sim.run_until(deadline)
        assert _displayed_at(sim, target, deadline) == TARGET_PRICE, seed
        assert check(sim, BOUND)['convergence'] == [], seed


def test_station_reconnecting_before_last_price_converges():
    for seed in SEEDS:
        sim = _simulation(seed)
        target = sim.station_ids[1]
        for sid in sim.station_ids:
            if sid != target:
                sim.force_reachable(sid, 0.0)
        sim.force_reachable(target, 25.0)
        _send_series(sim, target, ((30.5, 105), (30.8, 115), (SEND_TIME, TARGET_PRICE)))
        deadline = SEND_TIME + BOUND
        sim.run_until(deadline)
        assert _displayed_at(sim, target, deadline) == TARGET_PRICE, seed
        assert check(sim, BOUND)['convergence'] == [], seed


def test_every_station_converges_with_five_stations():
    for seed in SEEDS:
        sim = _simulation(seed, stations=5)
        for sid in sim.station_ids:
            sim.force_reachable(sid, 0.0)
        target = sim.station_ids[-1]
        _send_series(sim, target, ((30.5, 110), (30.9, 125), (SEND_TIME, TARGET_PRICE)))
        deadline = SEND_TIME + BOUND
        sim.run()
        assert _displayed_at(sim, target, deadline) == TARGET_PRICE, seed
        assert check(sim, BOUND)['convergence'] == [], seed
