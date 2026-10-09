import app
from nrvv_env import Simulation

STATION = 'S1'
PRICE = 1.459


def _service_for(sim):
    candidates = [
        obj for obj in vars(app).values()
        if isinstance(obj, type) and callable(getattr(obj, 'set_desired_price', None))
    ]
    assert len(candidates) == 1, 'app must expose exactly one service class'
    service = candidates[0](sim.send_price_update)
    sim.connect(service)
    return service


def test_one_publish_captures_exactly_one_update():
    sim = Simulation(1, [STATION, 'S2'], changes=0)
    _service_for(sim)
    sim.issue_desired_price(STATION, PRICE)
    assert len(sim.sends) == 1


def test_publish_is_addressed_to_s1_only():
    for seed in range(3):
        sim = Simulation(seed, [STATION, 'S2', 'S3'], changes=0)
        _service_for(sim)
        sim.issue_desired_price(STATION, PRICE)
        assert [s.station for s in sim.sends] == [STATION]
        sim.run()
        assert {d.station for d in sim.deliveries} == {STATION}
        assert sim.displayed('S2') is None
        assert sim.displayed('S3') is None


def test_publish_carries_desired_price_unchanged():
    for seed in range(5):
        sim = Simulation(seed, [STATION, 'S2'], changes=0)
        _service_for(sim)
        sim.issue_desired_price(STATION, PRICE)
        assert len(sim.sends) == 1
        sent = sim.sends[0]
        assert sent.station == STATION
        assert sent.price == PRICE
        assert sent.desired_at_send == PRICE


def test_single_update_stays_single_after_delivery():
    for seed in range(5):
        sim = Simulation(seed, [STATION, 'S2'], changes=0)
        _service_for(sim)
        sim.issue_desired_price(STATION, PRICE)
        sim.run()
        assert len(sim.sends) == 1
        assert sim.displayed(STATION) == PRICE
