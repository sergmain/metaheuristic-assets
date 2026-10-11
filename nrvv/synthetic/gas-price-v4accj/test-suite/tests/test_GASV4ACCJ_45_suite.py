# Verifies GASV4ACCJ-2: every desired price change is published to its station.
import importlib

import app
from nrvv_env import Simulation

SEEDS = range(1, 41)
WINDOW = 120.0


def _fresh_run(seed):
    importlib.reload(app)
    sim = Simulation(seed, changes=40, drop_probability=0.0)
    sim.connect(app)
    sim.run_until_quiet()
    sim.run_until(3000.0)
    return sim


def _quiet(sim, station, start):
    end = start + WINDOW
    return all(not (s < end and e > start) for s, e in sim.unreachable_intervals(station))


def _isolated_changes(sim):
    # Changes with no other change to the same station within WINDOW either side,
    # and no outage of the station during WINDOW after the change.
    schedule = sim.schedule()
    result = []
    for station in sim.stations:
        own = [(t, p) for t, s, p in schedule if s == station]
        for i, (t, p) in enumerate(own):
            prev_t, prev_p = own[i - 1] if i else (None, None)
            next_t = own[i + 1][0] if i + 1 < len(own) else None
            if prev_t is not None and t - prev_t < WINDOW:
                continue
            if next_t is not None and next_t - t < WINDOW:
                continue
            if not _quiet(sim, station, t):
                continue
            result.append((station, t, p, prev_p))
    return result


def _updates(sim, station, start):
    return [r for r in sim.sends() if r.station == station and start <= r.sent_at < start + WINDOW]


def _check_change(sim, station, t, price, prev_price):
    assert prev_price != price
    updates = _updates(sim, station, t)
    assert len(updates) == 1, f'{station} change at {t}: {len(updates)} updates sent'
    assert updates[0].price == price, f'{station} change at {t}: update carries {updates[0].price}, expected {price}'


def test_each_price_change_sends_exactly_one_update_to_its_station():
    checked = 0
    for seed in SEEDS:
        sim = _fresh_run(seed)
        for station, t, price, prev_price in _isolated_changes(sim):
            _check_change(sim, station, t, price, prev_price)
            checked += 1
    assert checked > 0, 'no seed produced an isolated change to check'


def test_repeated_and_other_station_changes_each_send_one_update():
    scenarios = 0
    for seed in SEEDS:
        sim = _fresh_run(seed)
        isolated = _isolated_changes(sim)
        per_station = {}
        for item in isolated:
            per_station.setdefault(item[0], []).append(item)
        repeated = any(len(items) >= 2 for items in per_station.values())
        other = len(per_station) >= 2
        if not (repeated and other):
            continue
        for station, t, price, prev_price in isolated:
            _check_change(sim, station, t, price, prev_price)
        scenarios += 1
    assert scenarios > 0, 'no seed produced repeated changes to one station and a change to another'
