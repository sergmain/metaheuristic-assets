import random

import app
from nrvv_env import Simulation, SETTLE_SECONDS, DURATION, convergence_violations

SEEDS = (1, 2, 3, 4, 5)
WAIT = SETTLE_SECONDS


def _server_class():
    for name in dir(app):
        obj = getattr(app, name)
        if isinstance(obj, type) and callable(getattr(obj, 'set_desired_price', None)):
            return obj
    raise AssertionError('app defines no class with set_desired_price')


def _server_factory(send):
    cls = _server_class()
    try:
        return cls(send)
    except TypeError:
        return cls(send_price_update=send)


def _sim(seed, duration=0):
    # duration 0: the simulation schedules no central price changes, the test does
    return Simulation(seed, _server_factory, duration=duration)


def _quiet_start(sim, sid, span):
    # first time t such that the station is reachable on the whole of [t, t + span]
    windows = sim.outages(sid, until=50000)
    for t in [0] + [end for _, end in windows]:
        if all(not (start <= t + span and end > t) for start, end in windows):
            return t
    raise AssertionError(f'no reachable window of {span}s for {sid}')


def _assert_reachable(sim, sid, start, end):
    assert all(sim.reachable(sid, t) for t in range(start, end + 1)), f'{sid} unreachable within [{start}, {end}]'


def _set_price(sim, time, sid, value):
    # the central price source's change, scheduled the way the simulation schedules them
    sim._push(time, 'price', (sid, value))


def _price(seed, salt):
    return random.Random(f'{seed}/{salt}').randint(1, 999)


def test_displayed_price_equals_desired_price_five_minutes_after_settling():
    for seed in SEEDS:
        sim = _sim(seed)
        sid = 'S1'
        t0 = _quiet_start(sim, sid, 2 * WAIT)
        end = t0 + 2 * WAIT
        p = _price(seed, 'P')
        _set_price(sim, t0, sid, p)
        _assert_reachable(sim, sid, t0, end)
        sim.run_until(end)
        assert sim.now == end
        assert sim.desired_price(sid) == p, f'seed {seed}: desired {sim.desired_price(sid)}, expected {p}'
        shown = sim.stations[sid].displayed_price
        assert shown == p, f'seed {seed}: {sid} shows {shown}, desired {p}'
        assert convergence_violations(sim) == []


def test_latest_desired_price_wins_when_changes_arrive_in_a_burst():
    for seed in SEEDS:
        sim = _sim(seed)
        sid = 'S2'
        t0 = _quiet_start(sim, sid, 5 + 2 * WAIT)
        last = t0 + 5
        end = last + 2 * WAIT
        rng = random.Random(f'{seed}/burst')
        for t in (t0, t0 + 1, t0 + 3):
            _set_price(sim, t, sid, rng.randint(1, 999))
        p = 1000 + seed
        _set_price(sim, last, sid, p)
        _assert_reachable(sim, sid, t0, end)
        sim.run_until(end)
        assert sim.desired_price(sid) == p, f'seed {seed}: desired {sim.desired_price(sid)}, expected {p}'
        shown = sim.stations[sid].displayed_price
        assert shown == p, f'seed {seed}: {sid} shows {shown}, desired {p}'
        assert convergence_violations(sim) == []


def test_reverting_to_a_previously_shown_price_converges_to_it():
    for seed in SEEDS:
        sim = _sim(seed)
        sid = 'S3'
        start = _quiet_start(sim, sid, 702 + 2 * WAIT)
        a = _price(seed, 'A')
        b = a % 999 + 1
        _set_price(sim, start, sid, a)
        _set_price(sim, start + 700, sid, b)
        _set_price(sim, start + 702, sid, a)
        end = start + 702 + 2 * WAIT
        _assert_reachable(sim, sid, start, end)
        sim.run_until(start + 2 * WAIT)
        assert sim.stations[sid].displayed_price == a, f'seed {seed}: first settle not shown'
        sim.run_until(end)
        assert sim.desired_price(sid) == a, f'seed {seed}: desired {sim.desired_price(sid)}, expected {a}'
        shown = sim.stations[sid].displayed_price
        assert shown == a, f'seed {seed}: {sid} shows {shown}, desired {a}'
        assert convergence_violations(sim) == []


def test_each_station_converges_on_its_own_settled_price():
    for seed in SEEDS:
        sim = _sim(seed)
        plan = {}
        for sid in sim.stations:
            t0 = _quiet_start(sim, sid, 2 * WAIT)
            plan[sid] = (t0 + 2 * WAIT, t0, _price(seed, sid))
        for sid, (end, t0, p) in plan.items():
            _set_price(sim, t0, sid, p)
            _assert_reachable(sim, sid, t0, end)
        for sid, (end, _, p) in sorted(plan.items(), key=lambda item: item[1][0]):
            sim.run_until(end)
            assert sim.desired_price(sid) == p, f'seed {seed}: {sid} desired {sim.desired_price(sid)}, expected {p}'
            shown = sim.stations[sid].displayed_price
            assert shown == p, f'seed {seed}: {sid} shows {shown}, desired {p}'
        assert convergence_violations(sim) == []


def test_convergence_holds_at_every_checkpoint_of_a_full_run():
    for seed in SEEDS[:3]:
        sim = _sim(seed, duration=DURATION)
        for t in range(0, DURATION + 1, 60):
            sim.run_until(t)
            violations = convergence_violations(sim)
            assert not violations, f'seed {seed}: ' + '; '.join(violations)
