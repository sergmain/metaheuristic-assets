# Tests for GASV4ACCJ-10: a station holds a price only after its acknowledgement arrives.

import app
from nrvv_env import Simulation


def _field(obj, *names):
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    raise AssertionError(f'{obj!r} has none of the fields {names}')


def _held_price(status):
    value = _field(status, 'held_price', 'held')
    return None if value is None else int(value)


def _outstanding_price(status):
    outstanding = _field(status, 'outstanding_send', 'outstanding')
    if outstanding is None:
        return None
    return int(_field(outstanding, 'price'))


def _quiet_seed(first_seed):
    # A seed whose station is reachable for the first three minutes, so no send is lost to an outage.
    for seed in range(first_seed, first_seed + 1000):
        sim = Simulation(seed, stations=('S',), changes=0, drop_probability=0.0)
        if all(sim.reachable('S', float(t)) for t in range(0, 181, 5)):
            return seed
    raise RuntimeError('no reachable seed found')


def _sends_at(sim, station, price):
    return [r for r in sim.sends() if r.station == station and r.price == price]


def _check_held_only_after_ack(seed):
    station = f'S{seed}'
    sim = Simulation(seed, stations=(station,), changes=0, drop_probability=0.0)
    sim.connect(app)

    # Update carrying 100; its acknowledgement is not delivered yet.
    app.set_desired_price(station, 100)
    while not _sends_at(sim, station, 100):
        assert sim.step(), 'server never sent the price 100 update'
    first = _sends_at(sim, station, 100)[0]
    assert _held_price(app.query_station_status(station)) != 100

    # Let the environment deliver the acknowledgement.
    while first.state != 'acked':
        assert sim.step(), 'acknowledgement for price 100 never arrived'
    assert _held_price(app.query_station_status(station)) == 100

    # Updates 200 and 300; only the acknowledgement for 300 is delivered. The
    # simulation is not stepped again, so the 200 acknowledgement never arrives.
    app.set_desired_price(station, 200)
    app.set_desired_price(station, 300)
    if not _sends_at(sim, station, 300):
        # The server may defer the send to its next slot; request that time directly.
        app.simulated_time_wake_up(sim.now + 60.0)
    sent_300 = _sends_at(sim, station, 300)
    assert sent_300, 'server never sent the price 300 update'
    assert _held_price(app.query_station_status(station)) == 100

    app.acknowledgement_received(station, sent_300[-1].send_id)
    status = app.query_station_status(station)
    assert _held_price(status) == 300
    assert _outstanding_price(status) != 200


def test_price_held_only_after_its_acknowledgement():
    for first_seed in (1, 2, 3):
        _check_held_only_after_ack(_quiet_seed(first_seed))
