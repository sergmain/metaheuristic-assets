import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)


def _build(sim):
    service_classes = [obj for obj in vars(app).values()
                       if isinstance(obj, type) and callable(getattr(obj, 'set_desired_price', None))]
    assert service_classes, 'app must provide a class offering set_desired_price'
    service_class = service_classes[0]
    try:
        service = service_class(sim.send_price_update)
    except TypeError:
        service = service_class()
    return sim.connect(service)


def _sim(seed, stations, **kwargs):
    return _build(Simulation(seed, stations, changes=0, **kwargs))


def _drive(sim, sequences):
    # issue each station's changes in turn, one round per step, then wait for quiescence
    rounds = max(len(prices) for prices in sequences.values())
    for i in range(rounds):
        for station, prices in sequences.items():
            if i < len(prices):
                sim.issue_desired_price(station, prices[i])
        sim.step()
    sim.run()
    assert not sim.pending()
    return sim


def test_station_a_and_b_end_on_their_latest_desired_prices():
    for seed in SEEDS:
        sim = _sim(seed, ['A', 'B'])
        _drive(sim, {'A': [1, 5, 2, 4], 'B': [3, 1, 5, 2]})
        assert sim.displayed('A') == 4, f'seed {seed}'
        assert sim.displayed('B') == 2, f'seed {seed}'


def test_station_returning_to_earlier_price_ends_on_that_price():
    for seed in SEEDS:
        sim = _sim(seed, ['A', 'B'])
        _drive(sim, {'A': [2, 4, 2], 'B': [5, 3, 5, 1, 5]})
        assert sim.displayed('A') == 2, f'seed {seed}'
        assert sim.displayed('B') == 5, f'seed {seed}'


def test_random_schedules_leave_every_station_showing_its_latest_desire():
    for seed in range(1, 21):
        sim = _build(Simulation(seed, ['A', 'B', 'C'], changes=30, horizon=40))
        sim.run()
        assert sim.desires, f'seed {seed}: schedule issued no changes'
        for station in ('A', 'B', 'C'):
            assert sim.displayed(station) == sim.desired(station), f'seed {seed} station {station}'


def test_changes_arriving_while_updates_are_in_flight_are_eventually_shown():
    for seed in SEEDS:
        sim = _sim(seed, ['A', 'B'], max_update_delay=6, max_ack_delay=6)
        sim.issue_desired_price('A', 1)
        sim.issue_desired_price('B', 2)
        sim.step()
        sim.issue_desired_price('A', 3)
        sim.step()
        sim.issue_desired_price('B', 4)
        sim.issue_desired_price('A', 5)
        sim.run()
        assert not sim.pending(), f'seed {seed}'
        assert sim.displayed('A') == 5, f'seed {seed}'
        assert sim.displayed('B') == 4, f'seed {seed}'


def test_every_station_converges_for_all_transport_delays():
    for max_update_delay in (1, 6):
        for max_ack_delay in (1, 6):
            for seed in SEEDS:
                sim = _sim(seed, ['A', 'B'],
                           max_update_delay=max_update_delay,
                           max_ack_delay=max_ack_delay)
                _drive(sim, {'A': [4, 1, 3], 'B': [2, 5, 2]})
                assert sim.displayed('A') == 3, f'seed {seed} delays {max_update_delay},{max_ack_delay}'
                assert sim.displayed('B') == 2, f'seed {seed} delays {max_update_delay},{max_ack_delay}'


def test_displayed_price_stays_at_latest_desire_once_quiescent():
    for seed in SEEDS:
        sim = _sim(seed, ['A', 'B'])
        _drive(sim, {'A': [5, 2], 'B': [1, 4, 3]})
        before = {station: sim.displayed(station) for station in ('A', 'B')}
        for _ in range(10):
            sim.step()
        after = {station: sim.displayed(station) for station in ('A', 'B')}
        assert before == {'A': 2, 'B': 3}, f'seed {seed}'
        assert after == before, f'seed {seed}'
