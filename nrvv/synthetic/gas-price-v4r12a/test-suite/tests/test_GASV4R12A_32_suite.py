'''GASV4R12A-6: the service converges every station to the latest desired price
without any change to the stations (criterion GASV4R12A-32).'''
import app
from nrvv_env import Simulation

OUTDATED = {'s1': 11, 's2': 22, 's3': 33, 's4': 44}
LATEST = {'s1': 111, 's2': 222, 's3': 333, 's4': 444}


def make_sim(seed, **kwargs):
    sim = Simulation(seed, stations=tuple(OUTDATED), **kwargs)
    sim.attach(lambda send: app.Server(send_update=send))
    return sim


def seed_outdated(sim):
    # Each station already displays a different, earlier price; nothing else is configured.
    for sid, price in OUTDATED.items():
        sim.stations[sid].apply(price)


def schedule_prices(sim, tick, prices):
    sim.source_schedule.setdefault(tick, []).extend(prices.items())


def test_every_station_shows_latest_price_on_reliable_transport():
    sim = make_sim(seed=1, change_rate=0, loss=0.0, fault_window=(0, 0))
    seed_outdated(sim)
    sim.source_schedule = {}
    schedule_prices(sim, 1, LATEST)

    report = sim.assert_converged()

    assert report.failures == []
    for sid in OUTDATED:
        assert sim.stations[sid].displayed == LATEST[sid]
        assert report.stations[sid]['displayed'] == LATEST[sid]
        assert report.stations[sid]['up_to_date'] is True


def test_every_station_converges_under_lossy_transport_for_several_seeds():
    for seed in (2, 3, 5, 8, 13):
        sim = make_sim(seed, change_rate=0, loss=0.5, fault_window=(1, 10))
        seed_outdated(sim)
        sim.source_schedule = {}
        schedule_prices(sim, 1, LATEST)

        report = sim.assert_converged()

        assert report.failures == [], 'seed {}'.format(seed)
        for sid in OUTDATED:
            assert sim.stations[sid].displayed == LATEST[sid], 'seed {}, {}'.format(seed, sid)


def test_latest_desired_price_replaces_every_earlier_price():
    intermediate = {sid: price + 1000 for sid, price in LATEST.items()}
    for seed in (4, 6, 7):
        sim = make_sim(seed, change_rate=0, loss=0.4, fault_window=(1, 10))
        seed_outdated(sim)
        sim.source_schedule = {}
        schedule_prices(sim, 1, intermediate)
        schedule_prices(sim, 3, LATEST)

        report = sim.assert_converged()

        assert sim.latest_desired() == LATEST
        assert report.failures == [], 'seed {}'.format(seed)
        for sid in OUTDATED:
            shown = sim.stations[sid].displayed
            assert shown == LATEST[sid], 'seed {}, {}'.format(seed, sid)
            assert shown != intermediate[sid]
            assert shown != OUTDATED[sid]


def test_random_price_changes_converge_to_latest_for_every_station():
    for seed in (21, 22, 23):
        sim = make_sim(seed, change_rate=0.3)
        seed_outdated(sim)
        # Guarantee every station receives at least one desired price.
        schedule_prices(sim, 1, LATEST)

        report = sim.assert_converged()

        latest = sim.latest_desired()
        assert set(latest) == set(OUTDATED), 'seed {}'.format(seed)
        assert report.failures == [], 'seed {}'.format(seed)
        for sid in OUTDATED:
            assert sim.stations[sid].displayed == latest[sid], 'seed {}, {}'.format(seed, sid)


def test_station_already_showing_latest_price_is_not_disturbed():
    sim = make_sim(seed=9, change_rate=0, loss=0.3, fault_window=(1, 10))
    seed_outdated(sim)
    sim.stations['s1'].apply(LATEST['s1'])
    sim.source_schedule = {}
    schedule_prices(sim, 1, LATEST)

    report = sim.assert_converged()

    assert report.failures == []
    for sid in OUTDATED:
        assert sim.stations[sid].displayed == LATEST[sid]
