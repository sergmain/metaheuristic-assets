import random

import app
from nrvv_env import Simulation

STATION = 's1'
SEEDS = (1, 2, 3, 4, 5)
OBSERVATION_TICKS = 300
STABLE_TICKS = 30


def _prices(seed):
    rng = random.Random(seed)
    p1 = rng.randint(1, 500)
    p2 = p1 + rng.randint(1, 500)
    return p1, p2


def _observe(seed, schedule, stations=(STATION,), max_delay=3):
    last_tick = max(schedule)
    sim = Simulation(seed, stations=stations, stop_tick=last_tick, fault_window=(0, 0),
                     max_delay=max_delay, loss=0.0)
    sim.source_schedule = schedule
    for sid in stations:
        sim.set_reachable(sid, True)
    sim.attach(lambda send: app.Server(send_update=send))
    history = []
    stable = 0
    while sim.now < OBSERVATION_TICKS:
        sim.step()
        history.append({sid: sim.stations[sid].displayed for sid in stations})
        if sim.now <= last_tick:
            continue
        if history[-1] == history[-2]:
            stable += 1
        else:
            stable = 0
        if stable >= STABLE_TICKS:
            break
    return sim, history


def test_station_displays_latest_price_after_it_is_superseded():
    for seed in SEEDS:
        p1, p2 = _prices(seed)
        sim, _ = _observe(seed, {1: [(STATION, p1)], 2: [(STATION, p2)]})
        assert sim.latest_desired() == {STATION: p2}
        shown = sim.stations[STATION].displayed
        assert shown == p2, 'seed {}: displayed {!r}, latest desired {!r}'.format(seed, shown, p2)


def test_latest_price_converges_for_every_transport_delay():
    for max_delay in (1, 2, 3, 5):
        for seed in SEEDS:
            p1, p2 = _prices(seed)
            sim, _ = _observe(seed, {1: [(STATION, p1)], 2: [(STATION, p2)]}, max_delay=max_delay)
            shown = sim.stations[STATION].displayed
            assert shown == p2, 'max_delay {}, seed {}: displayed {!r}, latest desired {!r}'.format(
                max_delay, seed, shown, p2)


def test_latest_price_converges_when_p1_was_already_displayed():
    for gap in (5, 12):
        for seed in SEEDS:
            p1, p2 = _prices(seed)
            sim, history = _observe(seed, {1: [(STATION, p1)], 1 + gap: [(STATION, p2)]})
            assert history[gap - 1][STATION] == p1, 'seed {}: P1 not displayed before P2'.format(seed)
            shown = sim.stations[STATION].displayed
            assert shown == p2, 'gap {}, seed {}: displayed {!r}, latest desired {!r}'.format(
                gap, seed, shown, p2)


def test_each_station_converges_to_its_own_latest_price():
    stations = ('s1', 's2')
    for seed in SEEDS:
        p1a, p2a = _prices(seed)
        p1b, p2b = _prices(seed + 100)
        schedule = {1: [('s1', p1a), ('s2', p1b)], 2: [('s1', p2a), ('s2', p2b)]}
        sim, _ = _observe(seed, schedule, stations=stations)
        assert sim.latest_desired() == {'s1': p2a, 's2': p2b}
        for sid, want in (('s1', p2a), ('s2', p2b)):
            shown = sim.stations[sid].displayed
            assert shown == want, 'seed {}, {}: displayed {!r}, latest desired {!r}'.format(
                seed, sid, shown, want)
