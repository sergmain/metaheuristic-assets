'''GASV4RDF1-42: at quiescence each station displays the latest desired price.'''

import pytest

import app
import nrvv_env


MAX_STEPS = 100000
SEEDS = range(25)

SCRIPTS = [
    [[('S1', 'P1'), ('S1', 'P2')]],
    [[('S1', 'P1'), ('S1', 'P2'), ('S1', 'P1'), ('S1', 'P2')]],
]


def _new_server(send_update, send_pricing_notice):
    for name in dir(app):
        candidate = getattr(app, name)
        if name[:1].isupper() and isinstance(candidate, type) and hasattr(candidate, 'set_desired_price'):
            return candidate(send_update, send_pricing_notice)
    pytest.fail('app defines no class with set_desired_price')


def _simulation(seed, **kwargs):
    return nrvv_env.Simulation(seed, _new_server, **kwargs)


def _run_to_quiet(sim):
    sim.run(max_steps=MAX_STEPS)
    assert sim.quiet, f'seed {sim.seed}: run did not reach quiescence'


def test_latest_desired_displayed_when_older_price_is_delivered_last():
    for script in SCRIPTS:
        for seed in SEEDS:
            sim = _simulation(seed, stations=['S1'], script=script)
            _run_to_quiet(sim)
            latest = sim.latest_desired('S1')
            assert latest == 'P2', f'seed {seed}: latest desired is {latest!r}'
            displayed = sim.displayed('S1')
            assert displayed == 'P2', f'seed {seed}: station displays {displayed!r}, expected "P2"'


def test_latest_desired_displayed_across_random_workloads():
    for seed in SEEDS:
        sim = _simulation(seed, stations=['S1', 'S2', 'S3'])
        _run_to_quiet(sim)
        touched = {call.station for call in sim.client_calls}
        assert touched, f'seed {seed}: no client calls were made'
        for station in sorted(touched):
            latest = sim.latest_desired(station)
            displayed = sim.displayed(station)
            assert displayed == latest, (
                f'seed {seed}: station {station} displays {displayed!r}, latest desired is {latest!r}')


def test_other_station_traffic_does_not_change_latest_desired_display():
    script = [
        [('S1', 'P1'), ('S2', 'P5'), ('S1', 'P2')],
        [('S2', 'P6'), ('S2', 'P7')],
    ]
    for seed in SEEDS:
        sim = _simulation(seed, stations=['S1', 'S2'], script=script)
        _run_to_quiet(sim)
        assert sim.latest_desired('S1') == 'P2', f'seed {seed}'
        assert sim.displayed('S1') == 'P2', f'seed {seed}: S1 displays {sim.displayed("S1")!r}'
        assert sim.displayed('S2') == sim.latest_desired('S2'), (
            f'seed {seed}: S2 displays {sim.displayed("S2")!r}, latest desired is {sim.latest_desired("S2")!r}')
