import inspect

import app
import nrvv_env


STATIONS = ('A', 'B', 'C')
SEEDS = range(8)


def _make_service(sim):
    # The service class is the one CapWords class of app that offers SetDesiredPrice.
    candidates = [
        obj for obj in vars(app).values()
        if inspect.isclass(obj) and callable(getattr(obj, 'set_desired_price', None))
    ]
    assert candidates, 'app must provide a service class with set_desired_price'
    return candidates[0](sim.send_price_update)


def _simulation(seed, stations=STATIONS, changes=0):
    sim = nrvv_env.Simulation(seed, stations, changes=changes)
    sim.connect(_make_service(sim))
    return sim


def test_single_price_update_is_displayed_by_station():
    sim = _simulation(1, ('A',))
    assert sim.displayed('A') is None

    sim.issue_desired_price('A', 4)
    sim.run()

    assert sim.displayed('A') == 4
    sent = [s.price for s in sim.sends if s.station == 'A']
    assert sent and sent[-1] == 4
    assert sim.deliveries[-1].station == 'A'
    assert sim.deliveries[-1].price == 4


def test_price_change_replaces_displayed_price():
    sim = _simulation(2, ('A',))

    sim.issue_desired_price('A', 2)
    sim.run()
    assert sim.displayed('A') == 2

    sim.issue_desired_price('A', 5)
    sim.run()
    assert sim.displayed('A') == 5

    shown = []
    for _, displayed in sim.history:
        if not shown or shown[-1] != displayed['A']:
            shown.append(displayed['A'])
    assert shown == [None, 2, 5]


def test_displayed_price_converges_to_desired_price_across_seeds():
    for seed in SEEDS:
        sim = _simulation(seed, STATIONS, changes=20).run()
        assert sim.desires, 'the schedule must issue desired prices'
        for station in STATIONS:
            desired = sim.desired(station)
            if desired is not None:
                assert sim.displayed(station) == desired, (seed, station)


def test_last_update_carries_the_desired_price_across_seeds():
    for seed in SEEDS:
        sim = _simulation(seed, STATIONS, changes=20).run()
        for station in STATIONS:
            sends = [s for s in sim.sends if s.station == station]
            if not sends:
                continue
            desired = sim.desired(station)
            assert sends[-1].price == desired, (seed, station)
            deliveries = [d for d in sim.deliveries if d.station == station]
            assert deliveries[-1].price == desired, (seed, station)
            assert deliveries[-1].displayed == desired, (seed, station)


def test_station_shows_exactly_what_each_update_carries():
    for seed in SEEDS:
        sim = _simulation(seed, STATIONS, changes=20).run()
        assert sim.deliveries
        for delivery in sim.deliveries:
            assert delivery.displayed == delivery.price, (seed, delivery)


def test_display_changes_only_when_an_update_is_delivered():
    for seed in SEEDS:
        sim = _simulation(seed, STATIONS, changes=20).run()
        previous = {station: None for station in STATIONS}
        for step, shown in sim.history:
            for station in STATIONS:
                if shown[station] != previous[station]:
                    assert any(
                        d.step == step and d.station == station and d.displayed == shown[station]
                        for d in sim.deliveries
                    ), (seed, step, station)
            previous = shown


def test_undesired_station_stays_unchanged():
    for seed in SEEDS:
        sim = _simulation(seed, ('A', 'B'))
        sim.issue_desired_price('A', 3)
        sim.run()
        assert sim.displayed('A') == 3
        assert sim.displayed('B') is None
        assert all(s.station == 'A' for s in sim.sends)


def test_sent_prices_are_desired_prices():
    for seed in SEEDS:
        sim = _simulation(seed, STATIONS, changes=20).run()
        for send in sim.sends:
            desired = {d.price for d in sim.desires if d.station == send.station}
            assert send.price in desired, (seed, send)


def test_latest_price_wins_when_changed_while_update_in_flight():
    for seed in SEEDS:
        sim = _simulation(seed, ('A',))
        sim.issue_desired_price('A', 1)
        sim.step()
        sim.issue_desired_price('A', 2)
        sim.run()
        assert sim.displayed('A') == 2, seed
        assert [s.price for s in sim.sends if s.station == 'A'][-1] == 2, seed
