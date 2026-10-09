import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)


def _make_service(sim):
    # The service class is not named in the interface, so find the one class of app
    # that offers set_desired_price and build it with the outbound port.
    service_class = None
    for name in dir(app):
        candidate = getattr(app, name)
        if name[:1].isupper() and isinstance(candidate, type) and hasattr(candidate, 'set_desired_price'):
            service_class = candidate
            break
    assert service_class is not None, 'app defines no class with set_desired_price'
    return service_class(sim.send_price_update)


def _connected(seed, stations, **kwargs):
    sim = Simulation(seed, stations, **kwargs)
    service = _make_service(sim)
    sim.connect(service)
    return sim, service


def _desired_in(state):
    # desired price taken from the result of inspect_station
    if state is None:
        return None
    if isinstance(state, dict):
        return state.get('desired')
    if hasattr(state, 'desired'):
        return state.desired
    return state[0]


def test_new_desired_price_accepted_while_update_unacknowledged():
    for seed in SEEDS:
        sim, service = _connected(seed, ['S1'], changes=0)
        sim.issue_desired_price('S1', 1)
        assert len(sim.sends) == 1
        assert sim.outstanding('S1') == 1
        time_before = sim.time
        sends_before = len(sim.sends)
        sim.issue_desired_price('S1', 3)
        # returned without any simulation step, without a new send and without cancelling the update
        assert sim.time == time_before
        assert len(sim.sends) == sends_before
        assert sim.outstanding('S1') == 1
        assert _desired_in(service.inspect_station('S1')) == 3
        assert sim.desired('S1') == 3


def test_new_desired_price_accepted_after_update_delivered_but_unacknowledged():
    for seed in SEEDS:
        sim, service = _connected(seed, ['S1'], changes=0)
        sim.issue_desired_price('S1', 1)
        assert len(sim.sends) == 1
        # advance until the update has reached the station but its acknowledgement is still outstanding
        for _ in range(20):
            if sim.outstanding('S1') == 1 and sim.in_transit('S1') == 0:
                break
            sim.step()
        assert sim.outstanding('S1') == 1 and sim.in_transit('S1') == 0, 'update never reached the station unacknowledged'
        time_before = sim.time
        sends_before = len(sim.sends)
        sim.issue_desired_price('S1', 4)
        assert sim.time == time_before
        assert len(sim.sends) == sends_before
        assert sim.outstanding('S1') == 1
        assert _desired_in(service.inspect_station('S1')) == 4
        sim.run()
        assert _desired_in(service.inspect_station('S1')) == 4


def test_overlapping_desired_prices_all_accepted_and_latest_kept():
    for seed in SEEDS:
        sim, service = _connected(seed, ['S1'], changes=0)
        sim.issue_desired_price('S1', 1)
        assert sim.outstanding('S1') == 1
        # several new prices, each submitted while the first update remains unacknowledged
        for price in (2, 3, 4, 5):
            sim.issue_desired_price('S1', price)
            assert sim.outstanding('S1') == 1
            assert _desired_in(service.inspect_station('S1')) == price
        sim.run()
        assert _desired_in(service.inspect_station('S1')) == 5
        assert sim.desired('S1') == 5


def test_desired_value_matches_latest_submission_after_random_changes():
    for seed in SEEDS:
        sim, service = _connected(seed, ['S1', 'S2', 'S3'], changes=30, horizon=40)
        sim.run()
        for station in ('S1', 'S2', 'S3'):
            assert _desired_in(service.inspect_station(station)) == sim.desired(station)
