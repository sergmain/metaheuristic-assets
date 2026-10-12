'''GASV4R12A-11: per-station desired price register with monotonic version.'''
import random

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)


def _pick(status, *names):
    for name in names:
        if isinstance(status, dict) and name in status:
            return status[name]
        if hasattr(status, name):
            return getattr(status, name)
    raise KeyError('status has none of {}'.format(names))


def _desired_price(status):
    return _pick(status, 'desired_price', 'desired')


def _desired_version(status):
    return _pick(status, 'desired_version', 'version')


def _new_sim(seed, stations=('s1', 's2')):
    # No source changes and no faults: only the test drives the server.
    sim = Simulation(seed, stations=stations, stop_tick=5,
                     fault_window=(0, 0), change_rate=0.0)
    sim.attach(lambda send: app.Server(send_update=send))
    return sim


def test_second_price_overwrites_first_without_waiting():
    for seed in SEEDS:
        for mode in ('in_flight', 'acknowledged'):
            sim = _new_sim(seed)
            server = sim.server
            p1, p2 = 100 + seed, 900 + seed
            server.accept_desired_price('s1', p1)
            sim.step()  # server sends P1 under its send rules
            if mode == 'acknowledged':
                sim.run_until_idle()  # P1 delivered and acknowledged
            v1 = _desired_version(server.query_station_status('s1'))

            server.accept_desired_price('s1', p2)  # must not wait or raise

            status = server.query_station_status('s1')
            assert _desired_price(status) == p2, (seed, mode)
            assert _desired_version(status) == v1 + 1, (seed, mode)

            sim.run_until_idle()  # late P1 acknowledgement must not revert the register
            status = server.query_station_status('s1')
            assert _desired_price(status) == p2, (seed, mode)
            assert _desired_version(status) == v1 + 1, (seed, mode)


def test_station_converges_to_second_price_never_first():
    for seed in SEEDS:
        sim = _new_sim(seed)
        server = sim.server
        p1, p2 = 100 + seed, 900 + seed
        server.accept_desired_price('s1', p1)
        sim.step()
        server.accept_desired_price('s1', p2)
        sim.converge()
        assert sim.stations['s1'].displayed == p2, seed
        assert _desired_price(server.query_station_status('s1')) == p2, seed


def test_other_station_price_leaves_station_unchanged():
    for seed in SEEDS:
        sim = _new_sim(seed)
        server = sim.server
        server.accept_desired_price('s1', 100 + seed)
        sim.step()
        before = server.query_station_status('s1')
        price, version = _desired_price(before), _desired_version(before)

        server.accept_desired_price('s2', 500 + seed)
        after = server.query_station_status('s1')
        assert _desired_price(after) == price, seed
        assert _desired_version(after) == version, seed

        sim.step()
        after = server.query_station_status('s1')
        assert _desired_price(after) == price, seed
        assert _desired_version(after) == version, seed


def test_desired_version_increases_by_one_per_accepted_price():
    for seed in SEEDS:
        sim = _new_sim(seed, stations=('s1',))
        server = sim.server
        rng = random.Random(seed)
        previous = None
        for _ in range(8):
            price = rng.randint(1, 1000)
            server.accept_desired_price('s1', price)
            status = server.query_station_status('s1')
            version = _desired_version(status)
            assert _desired_price(status) == price, seed
            if previous is not None:
                assert version == previous + 1, seed
            previous = version
            if rng.random() < 0.5:
                sim.step()
