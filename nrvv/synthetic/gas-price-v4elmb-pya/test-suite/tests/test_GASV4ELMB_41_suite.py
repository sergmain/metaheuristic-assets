import app
from nrvv_env import Simulation, default_view

SEEDS = (1, 2, 3, 4, 5)


def _setup(seed):
    sim = Simulation(seed, lambda send: app.Service(send))
    station = sim.station_ids[seed % len(sim.station_ids)]
    first = sim.rng.randint(0, 20)
    second = first + 1 + sim.rng.randint(0, 19)
    return sim, station, first, second


def _send_two_updates(sim, station, first, second):
    sim.service.set_desired_price(station, first)
    sim.service.set_desired_price(station, second)
    sends = [s for s in sim.sends if s.station == station]
    assert len(sends) >= 2, 'expected updates U1 and U2 to be sent to the station'
    u1, u2 = sends[0], sends[1]
    assert (u1.seq, u1.price) == (1, first)
    assert (u2.seq, u2.price) == (2, second)


def test_later_ack_alone_leaves_later_update_not_acknowledged():
    for seed in SEEDS:
        sim, station, first, second = _setup(seed)
        _send_two_updates(sim, station, first, second)
        sim.service.ack_received(station, 2)
        view = default_view(sim.query(station))
        assert view['in_flight_seq'] is not None, (
            'U2 reported acknowledged although only its acknowledgement was received (seed %d)' % seed)


def test_earlier_ack_after_later_ack_marks_both_updates_acknowledged():
    for seed in SEEDS:
        sim, station, first, second = _setup(seed)
        _send_two_updates(sim, station, first, second)
        sim.service.ack_received(station, 2)
        sim.service.ack_received(station, 1)
        view = default_view(sim.query(station))
        assert view['in_flight_seq'] is None, (
            'U1 and U2 not both acknowledged after both acknowledgements arrived (seed %d)' % seed)
        assert view['shown_price'] == second, (
            'acknowledged price not shown after both acknowledgements (seed %d)' % seed)
