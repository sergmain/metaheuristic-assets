# GASV4CRT1-33: an acknowledgement confirms the price only when it matches the in-flight price.
import app
from nrvv_env import Simulation

STATION = 'S1'
SEEDS = range(5)
FACTORY_NAMES = ('PriceService', 'PricingService', 'StationPriceService', 'Service', 'build_service', 'make_service', 'create_service')


def _new_service(port):
    for name in FACTORY_NAMES:
        factory = getattr(app, name, None)
        if factory is not None:
            return factory(port)
    raise AssertionError('app provides no service factory taking the outbound port')


def _start(seed):
    sim = Simulation(seed, [STATION], changes=0)
    service = _new_service(sim.send_price_update)
    sim.connect(service)
    return sim, service


def _read(state, names, index):
    if state is None:
        return None
    if isinstance(state, dict):
        for name in names:
            if name in state:
                return state[name]
        return None
    for name in names:
        if hasattr(state, name):
            return getattr(state, name)
    return state[index]


def _state(service, station):
    # (desired, confirmed, in_flight) as the service holds them
    state = service.inspect_station(station)
    return (_read(state, ('desired', 'desired_price'), 0),
            _read(state, ('confirmed', 'confirmed_price'), 1),
            _read(state, ('in_flight', 'in_flight_price', 'inflight'), 2))


def test_matching_ack_confirms_and_mismatched_ack_is_ignored():
    for seed in SEEDS:
        sim, service = _start(seed)

        sim.issue_desired_price(STATION, 10.00)
        sim.run()
        assert _state(service, STATION) == (10.00, 10.00, None)

        sim.issue_desired_price(STATION, 12.50)
        assert _state(service, STATION) == (12.50, 10.00, 12.50)

        sim.run()  # the station shows 12.50 and acknowledges it
        assert sim.acks[-1].price == 12.50
        assert _state(service, STATION) == (12.50, 12.50, None)

        sim.issue_desired_price(STATION, 15.00)
        assert _state(service, STATION) == (15.00, 12.50, 15.00)
        sends_before = len(sim.sends)
        displayed_before = sim.displayed(STATION)

        service.receive_acknowledgement(STATION, 14.00)

        assert _state(service, STATION) == (15.00, 12.50, 15.00)
        assert len(sim.sends) == sends_before
        assert sim.displayed(STATION) == displayed_before


def test_mismatched_ack_leaves_slot_open_for_matching_ack():
    for seed in SEEDS:
        sim, service = _start(seed)

        sim.issue_desired_price(STATION, 15.00)
        assert _state(service, STATION) == (15.00, None, 15.00)

        service.receive_acknowledgement(STATION, 14.00)
        assert _state(service, STATION) == (15.00, None, 15.00)

        service.receive_acknowledgement(STATION, 15.00)
        assert _state(service, STATION) == (15.00, 15.00, None)
