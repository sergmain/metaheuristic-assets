import importlib

import app
from nrvv_env import Simulation

SEEDS = range(1, 31)
STATION = 'S0'
MAX_TICKS = 5000
OBSERVATIONS = 40


def _fresh_app():
    # reload resets the module-level state of app for each run; app's source is not changed
    return importlib.reload(app)


def _reachable_sim(seed, stations=1):
    sim = Simulation(_fresh_app(), seed, stations=stations)
    for s in sim.station_ids:
        sim.outages[s] = []
    return sim


def _scripted_sim(seed, changes):
    sim = _reachable_sim(seed)
    sim.script = [(t, STATION, p) for t, p in changes]
    sim._script_by_tick = {}
    for t, s, p in sim.script:
        sim._script_by_tick.setdefault(t, []).append((s, p))
    sim.last_change_tick = max(t for t, _ in changes)
    return sim


def _shown(sim, station):
    return sim.server_state(station)['shown_price']


def test_single_station_ends_showing_latest_desired_price():
    for seed in SEEDS:
        sim = _reachable_sim(seed)
        sim.run(max_ticks=MAX_TICKS)
        want = sim.final_desired(STATION)
        assert len(sim.desired[STATION]) >= 2, seed
        assert sim.stations[STATION].price == want, seed
        assert _shown(sim, STATION) == want, seed


def test_displayed_price_stays_at_latest_desired_price_in_later_observations():
    for seed in SEEDS:
        sim = _reachable_sim(seed)
        sim.run(max_ticks=MAX_TICKS)
        want = sim.final_desired(STATION)
        for _ in range(OBSERVATIONS):
            sim.step()
            assert sim.stations[STATION].price == want, seed
            assert _shown(sim, STATION) == want, seed


def test_every_reachable_station_ends_showing_its_latest_desired_price():
    for seed in SEEDS:
        sim = _reachable_sim(seed, stations=3)
        sim.run(max_ticks=MAX_TICKS)
        assert sim.final_display_mismatches() == [], seed
        for s in sim.station_ids:
            assert _shown(sim, s) == sim.final_desired(s), seed


def test_later_price_replaces_earlier_price_after_it_was_shown():
    for seed in SEEDS:
        sim = _scripted_sim(seed, [(1, 5), (60, 11)])
        sim.run(max_ticks=MAX_TICKS)
        assert sim.stations[STATION].price == 11, seed
        assert _shown(sim, STATION) == 11, seed


def test_later_price_sent_while_earlier_update_is_in_flight_converges():
    for seed in SEEDS:
        sim = _scripted_sim(seed, [(1, 5), (2, 11)])
        sim.run(max_ticks=MAX_TICKS)
        assert sim.stations[STATION].price == 11, seed
        assert _shown(sim, STATION) == 11, seed
