import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)
SERVICE_OPERATIONS = ('set_desired_price', 'receive_acknowledgement', 'inspect_station')


def _connect_service(sim):
    for name in dir(app):
        candidate = getattr(app, name)
        if isinstance(candidate, type) and all(hasattr(candidate, op) for op in SERVICE_OPERATIONS):
            return sim.connect(candidate(sim.send_price_update))
    raise AssertionError('app defines no class offering the service operations')


def test_repeated_confirmed_price_sends_no_update():
    for seed in SEEDS:
        sim = Simulation(seed, ['S1'], changes=0)
        _connect_service(sim)

        sim.issue_desired_price('S1', 1.499)
        sim.run()
        assert sim.displayed('S1') == 1.499
        assert [s.price for s in sim.sends] == [1.499]

        sends_before = len(sim.sends)
        deliveries_before = len(sim.deliveries)
        sim.issue_desired_price('S1', 1.499)
        sim.run()

        assert len(sim.sends) == sends_before
        assert len(sim.deliveries) == deliveries_before
        assert sim.displayed('S1') == 1.499
        assert sim.desired('S1') == 1.499
        assert sim.outstanding('S1') == 0


def test_no_update_carries_the_confirmed_price():
    total_sends = 0
    for seed in SEEDS:
        sim = Simulation(seed, ['S1', 'S2', 'S3'])
        _connect_service(sim)
        sim.run()
        total_sends += len(sim.sends)
        for send in sim.sends:
            assert send.confirmed_at_send != send.price
    assert total_sends > 0
