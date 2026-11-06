import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 5, 8, 13, 21, 34)


def _service_class():
    for value in vars(app).values():
        if isinstance(value, type) and hasattr(value, 'set_desired_price') and hasattr(value, 'receive_acknowledgement'):
            return value
    raise AssertionError('app defines no service class with set_desired_price and receive_acknowledgement')


def _build(seed, stations, **kwargs):
    sim = Simulation(seed, stations, **kwargs)
    sim.connect(_service_class()(sim.send_price_update))
    return sim


def _sent_prices(sim, station):
    return [s.price for s in sim.sends if s.station == station]


def test_same_price_not_resent_while_update_in_flight():
    sim = _build(7, ['S1'], changes=0)
    sim.issue_desired_price('S1', 3)
    assert _sent_prices(sim, 'S1') == [3]
    sim.issue_desired_price('S1', 3)
    assert _sent_prices(sim, 'S1') == [3]
    assert sim.outstanding('S1') == 1
    assert sim.in_transit('S1') == 1
    sim.run()
    assert _sent_prices(sim, 'S1') == [3]
    assert sim.displayed('S1') == 3


def test_same_price_not_resent_before_acknowledgement_arrives():
    sim = _build(11, ['S1'], changes=0, max_update_delay=1, max_ack_delay=4)
    sim.issue_desired_price('S1', 3)
    sim.step()
    assert sim.displayed('S1') == 3
    assert sim.in_transit('S1') == 0
    assert sim.outstanding('S1') == 1
    assert sim.acks == []
    sim.issue_desired_price('S1', 3)
    assert _sent_prices(sim, 'S1') == [3]
    sim.run()
    assert _sent_prices(sim, 'S1') == [3]
    assert len(sim.acks) == 1


def test_different_price_sent_once_pending_acknowledgement_clears():
    sim = _build(3, ['S1'], changes=0)
    sim.issue_desired_price('S1', 3)
    sim.issue_desired_price('S1', 5)
    assert _sent_prices(sim, 'S1') == [3]
    assert sim.in_transit('S1') == 1
    sim.run()
    assert _sent_prices(sim, 'S1') == [3, 5]
    second = sim.sends[1]
    assert second.outstanding_before == 0
    assert second.confirmed_at_send == 3
    assert sim.displayed('S1') == 5


def test_no_send_while_an_update_is_unacknowledged_across_seeds():
    for seed in SEEDS:
        sim = _build(seed, ['A', 'B', 'C'], changes=60, prices=(1, 2))
        sim.run()
        assert sim.sends, f'seed {seed}: no updates were sent'
        for send in sim.sends:
            assert send.outstanding_before == 0, f'seed {seed}: {send}'


def test_latest_different_price_is_eventually_sent_across_seeds():
    for seed in SEEDS:
        sim = _build(seed, ['A', 'B', 'C'], changes=60, prices=(1, 2))
        sim.run()
        for station in ('A', 'B', 'C'):
            desired = sim.desired(station)
            if desired is not None:
                assert sim.displayed(station) == desired, f'seed {seed}, station {station}'
