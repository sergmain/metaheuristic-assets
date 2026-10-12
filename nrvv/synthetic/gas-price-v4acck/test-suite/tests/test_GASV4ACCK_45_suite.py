'''GASV4ACCK-45: stop-and-wait per station (GASV4ACCK-10).

Driven only through nrvv_env. The server is found as the class of app that offers set_latest_price.
'''

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)
STATIONS = ('S1', 'S2', 'S3')
LIMIT = 2000
WIDE_PRICES = (1, 10 ** 6)


def _make_server():
    for name in dir(app):
        candidate = getattr(app, name)
        if isinstance(candidate, type) and callable(getattr(candidate, 'set_latest_price', None)):
            return candidate()
    raise AssertionError('app provides no server class with set_latest_price')


def _bound_simulation(seed, stations, **kwargs):
    sim = Simulation(seed, stations, **kwargs)
    server = _make_server()
    sim.bind(server)
    dispatch = server.send_price_update

    def checked_dispatch(station, price):
        # Stop-and-wait: nothing may be dispatched to a station while its previous update is unacknowledged.
        outstanding = [r for r in sim.unacknowledged_sends() if r.station == station]
        assert not outstanding, f'{station}: {price!r} dispatched while {len(outstanding)} update(s) await ack'
        dispatch(station, price)

    server.send_price_update = checked_dispatch
    return sim


def _two_updates(seed):
    # Window 0 puts both changes at logical time 0, in submission order P1 then P2.
    sim = _bound_simulation(seed, ['S1'], window=0, changes_per_station=(2, 2), price_range=WIDE_PRICES)
    sim.step()
    p1, p2 = (c.price for c in sim.changes)
    assert p1 != p2, f'seed {seed}: prices must differ for the check to mean anything'
    return sim, p1, p2


def _step_until(sim, done):
    while not done():
        assert sim.now < LIMIT, 'expected event never happened'
        sim.step()


def _run_to_end_checked(sim):
    steps = 0
    while sim.now <= sim.end_time or sim.in_flight:
        assert steps < sim.max_steps, 'simulation did not settle'
        sim.step()
        steps += 1


def test_second_update_not_dispatched_before_first_acknowledged():
    for seed in SEEDS:
        sim, p1, _ = _two_updates(seed)
        assert [(r.station, r.price) for r in sim.sends] == [('S1', p1)], f'seed {seed}'
        while not sim.acknowledgements:
            assert len(sim.sends) == 1, f'seed {seed}: second update dispatched before first acknowledged'
            sim.step()
            assert sim.now < LIMIT, f'seed {seed}: first acknowledgement never arrived'


def test_second_update_dispatched_on_first_acknowledgement_and_held_after_its_ack():
    for seed in SEEDS:
        sim, _, p2 = _two_updates(seed)
        _step_until(sim, lambda: sim.acknowledgements)
        assert len(sim.sends) == 2, f'seed {seed}: second update not dispatched on first acknowledgement'
        assert sim.sends[1].price == p2, f'seed {seed}: wrong update dispatched second'
        assert sim.sends[1].sent_at == sim.acknowledgements[0][0], f'seed {seed}'
        _step_until(sim, lambda: len(sim.acknowledgements) == 2)
        assert sim.held_prices()['S1'] == p2, f'seed {seed}: held price is not P2 after its acknowledgement'


def test_one_outstanding_update_per_station_across_repeated_updates():
    for seed in SEEDS:
        sim = _bound_simulation(seed, STATIONS, changes_per_station=(1, 6))
        _run_to_end_checked(sim)
        assert not sim.unacknowledged_sends(), f'seed {seed}: updates never acknowledged'
        assert all(count >= 1 for count in sim.send_counts().values()), f'seed {seed}: station never updated'


def test_held_price_equals_last_dispatched_update():
    for seed in SEEDS:
        sim = _bound_simulation(seed, STATIONS, changes_per_station=(1, 6))
        _run_to_end_checked(sim)
        held = sim.held_prices()
        for station in STATIONS:
            sends = [r for r in sim.sends if r.station == station]
            assert held[station] == sends[-1].price, f'seed {seed}: {station} holds a price other than the last dispatched'
            assert held[station] == sim.reference_final_prices[station], f'seed {seed}: {station} final price wrong'


def test_stations_are_outstanding_independently():
    for seed in SEEDS:
        sim = _bound_simulation(seed, ['S1', 'S2'], window=0, changes_per_station=(1, 1), price_range=WIDE_PRICES)
        sim.step()
        assert sorted(r.station for r in sim.sends) == ['S1', 'S2'], f'seed {seed}: one station waited on another'
        assert all(r.acknowledged_at is None for r in sim.sends), f'seed {seed}'
