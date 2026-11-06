import app
from nrvv_env import Simulation


def test_price_update_shown_by_unmodified_station():
    sim = Simulation(app, seed=1, loss=0.0, outage=0.0)
    station = sim.stations['S1']
    assert station.displayed is None
    assert station.outages == []
    sim.set_desired_price('S1', 42)
    assert sim.quiesce()
    assert sim.displayed('S1') == 42
    assert sim.last_delivered_price('S1') == 42
    assert station.station_id == 'S1'
    assert station.outages == []


def test_price_update_eventually_delivered_and_shown_under_loss_and_outage():
    for seed in range(20):
        sim = Simulation(app, seed=seed)
        sim.set_desired_price('S2', 77)
        for _ in range(400):
            if sim.displayed('S2') == 77:
                break
            sim.tick()
        assert sim.displayed('S2') == 77, f'seed {seed}'


def test_delivery_adds_no_message_beyond_price_updates():
    for seed in range(10):
        sim = Simulation(app, seed=seed)
        sim.run_schedule(steps=60)
        issued = {(station_id, price) for _, station_id, price in sim.desired_history}
        for entry in sim.sent:
            assert (entry['station'], entry['price']) in issued, f'seed {seed}'
        for station_id, station in sim.stations.items():
            for _, price in station.received:
                assert (station_id, price) in issued, f'seed {seed}'


def test_station_acknowledges_each_delivery_without_modification():
    for seed in range(10):
        sim = Simulation(app, seed=seed, loss=0.0)
        sim.run_schedule(steps=40)
        assert sim.quiesce(bound=800), f'seed {seed}'
        acks = sim.acks_per_station()
        for station_id, station in sim.stations.items():
            assert acks[station_id] == station.acks_returned, f'seed {seed}'


def test_every_station_shows_its_latest_price():
    for seed in range(10):
        sim = Simulation(app, seed=seed, loss=0.0, outage=0.0)
        latest = {}
        for station_id, price in [('S1', 10 + seed), ('S2', 20 + seed), ('S3', 30 + seed)]:
            sim.set_desired_price(station_id, price)
            latest[station_id] = price
        assert sim.quiesce(), f'seed {seed}'
        for station_id, price in latest.items():
            assert sim.displayed(station_id) == price, f'seed {seed}'
            assert sim.stations[station_id].outages == []
