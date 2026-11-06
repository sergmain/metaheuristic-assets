import inspect

import app
from nrvv_env import Simulation

SEEDS = (0, 1, 2, 3, 4)
STATIONS = ('S1', 'S2')


def _part(state, names, index):
    for name in names:
        if isinstance(state, dict) and name in state:
            return state[name]
        if hasattr(state, name):
            return getattr(state, name)
    return state[index]


def _inspect(service, station):
    state = service.inspect_station(station)
    return (_part(state, ('desired', 'desired_price'), 0),
            _part(state, ('confirmed', 'confirmed_price'), 1),
            _part(state, ('in_flight', 'in_flight_price', 'inflight'), 2))


def _make_service(send_price_update):
    for name in dir(app):
        candidate = getattr(app, name)
        if (inspect.isclass(candidate)
                and hasattr(candidate, 'set_desired_price')
                and hasattr(candidate, 'receive_acknowledgement')
                and hasattr(candidate, 'inspect_station')):
            return candidate(send_price_update)
    raise AssertionError('app defines no service class with the required operations')


def test_price_not_confirmed_before_acknowledgement():
    for seed in SEEDS:
        sim = Simulation(seed, STATIONS, changes=0)
        service = _make_service(sim.send_price_update)
        sim.connect(service)
        sim.issue_desired_price('S1', 4)
        assert len(sim.sends) == 1 and sim.sends[0].price == 4
        _, confirmed, in_flight = _inspect(service, 'S1')
        assert confirmed is None
        assert in_flight == 4
        assert sim.displayed('S1') is None


def test_price_confirmed_only_when_acknowledgement_delivered():
    for seed in SEEDS:
        sim = Simulation(seed, STATIONS, changes=0)
        service = _make_service(sim.send_price_update)
        sim.connect(service)
        sim.issue_desired_price('S1', 4)
        for _ in range(200):
            sim.step()
            if any(a.station == 'S1' and a.price == 4 for a in sim.acks):
                break
            assert _inspect(service, 'S1')[1] is None
        else:
            raise AssertionError('acknowledgement never delivered')
        assert _inspect(service, 'S1')[1] == 4
        assert sim.displayed('S1') == 4


def test_acknowledgements_processed_in_arrival_order():
    for seed in SEEDS:
        sim = Simulation(seed, STATIONS, changes=0, max_update_delay=1, max_ack_delay=1)
        service = _make_service(sim.send_price_update)
        sim.connect(service)
        sim.issue_desired_price('S1', 1)
        sim.issue_desired_price('S1', 2)
        assert [s.price for s in sim.sends] == [1]
        sim._queue_ack('S1', 1, sim.time)
        sim._queue_ack('S1', 2, sim.time)
        sim.step()
        acked = [a.price for a in sim.acks if a.station == 'S1']
        assert acked == [1, 2]
        assert _inspect(service, 'S1')[1] == 2


def test_confirmed_price_always_acknowledged_and_settles():
    for seed in range(10):
        sim = Simulation(seed, STATIONS)
        service = _make_service(sim.send_price_update)
        sim.connect(service)
        for _ in range(10000):
            if not sim.pending():
                break
            sim.step()
            for station in STATIONS:
                confirmed = _inspect(service, station)[1]
                if confirmed is not None:
                    assert any(a.station == station and a.price == confirmed for a in sim.acks)
        else:
            raise AssertionError('simulation did not quiesce')
        for station in STATIONS:
            desired, confirmed, in_flight = _inspect(service, station)
            assert desired == sim.desired(station)
            assert in_flight is None
            assert confirmed == desired == sim.displayed(station)
