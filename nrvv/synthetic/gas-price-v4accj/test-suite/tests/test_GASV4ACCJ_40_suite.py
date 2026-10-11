"""GASV4ACCJ-40: the service reaches the latest desired price without station-side versioning or dedup."""

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)
TAIL = 3600.0
HORIZON = 1800.0


def _make_sim(seed, tag, drop_probability):
    stations = tuple(f"{tag}-{seed}-S{i}" for i in range(1, 4))
    sim = Simulation(seed, stations=stations, drop_probability=drop_probability)
    sim.connect(app)
    return sim


def _last_two_changes(sim):
    for station in sim.stations:
        planned = [(when, price) for when, s, price in sim.schedule() if s == station]
        if len(planned) >= 2:
            return station, planned[-2], planned[-1]
    raise AssertionError("seed plans no station with two price changes")


def _delivery_of(sim, station, price, sent_after):
    for record in sim.deliveries():
        if record.station == station and record.price == price and record.sent_at >= sent_after:
            return record
    return None


def test_stale_and_duplicate_redelivery_still_leaves_latest_price():
    for seed in SEEDS:
        sim = _make_sim(seed, "redeliver", drop_probability=0.0)
        station, (_, price_a), (time_b, price_b) = _last_two_changes(sim)
        sim.run_until(time_b)
        # Wait until the update carrying B has been delivered and the station is reachable.
        b_record = _delivery_of(sim, station, price_b, time_b)
        while b_record is None or not sim.reachable(station):
            if not sim.step():
                break
            b_record = _delivery_of(sim, station, price_b, time_b)
        assert b_record is not None and sim.reachable(station), (
            f"seed {seed}: B was not delivered to a reachable station")

        # The stale A is delivered again after B, and B is delivered a second time.
        sim.send_price_update(station, price_a, ("stale", seed))
        stale = sim.sends()[-1]
        sim.send_price_update(station, price_b, ("duplicate", seed))
        duplicate = sim.sends()[-1]
        sim.run_until(sim.now + TAIL)

        assert stale.delivery_order is not None and duplicate.delivery_order is not None, (
            f"seed {seed}: injected deliveries did not complete")
        assert stale.delivery_order > b_record.delivery_order, (
            f"seed {seed}: stale A was not delivered after B")
        assert sim.desired_price(station) == price_b
        assert sim.applied_price(station) == price_b, (
            f"seed {seed}: applied {sim.applied_price(station)}, expected {price_b}")


def test_every_station_settles_on_latest_price_under_loss_and_reordering():
    for seed in SEEDS:
        sim = _make_sim(seed, "settle", drop_probability=0.15)
        sim.run_until(HORIZON + TAIL)
        for station in sim.stations:
            assert sim.applied_price(station) == sim.desired_price(station), (
                f"seed {seed}: station {station} applied {sim.applied_price(station)}, "
                f"desired {sim.desired_price(station)}")
