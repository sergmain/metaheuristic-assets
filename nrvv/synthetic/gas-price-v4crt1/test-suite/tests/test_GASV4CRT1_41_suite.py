"""Verifies GASV4CRT1-11: per-station record of desired, confirmed and in-flight price."""
import inspect

import app
import nrvv_env


DESIRED_ALIASES = ('desired', 'desired_price', 'latest_desired', 'latest_desired_price')
CONFIRMED_ALIASES = ('confirmed', 'confirmed_price')
IN_FLIGHT_ALIASES = ('in_flight', 'in_flight_price', 'inflight', 'inflight_price')


def _pick(state, index, aliases):
    if isinstance(state, dict):
        for name in aliases:
            if name in state:
                return state[name]
        raise AssertionError('inspect result has no key among %r' % (aliases,))
    if isinstance(state, (tuple, list)):
        return state[index]
    for name in aliases:
        if hasattr(state, name):
            return getattr(state, name)
    raise AssertionError('inspect result has no field among %r' % (aliases,))


def _read(service, station):
    state = service.inspect_station(station)
    return (
        _pick(state, 0, DESIRED_ALIASES),
        _pick(state, 1, CONFIRMED_ALIASES),
        _pick(state, 2, IN_FLIGHT_ALIASES),
    )


def _service_class():
    for name, obj in vars(app).items():
        if (inspect.isclass(obj) and name[:1].isupper()
                and hasattr(obj, 'set_desired_price') and hasattr(obj, 'inspect_station')):
            return obj
    raise AssertionError('app defines no class with set_desired_price and inspect_station')


def _connected(seed, stations):
    sim = nrvv_env.Simulation(seed, stations, changes=0)
    cls = _service_class()
    try:
        service = cls(sim.send_price_update)
    except TypeError:
        service = cls()
    sim.connect(service)
    return sim, service


def test_new_station_reads_all_three_values_none():
    sim, service = _connected(1, ['S1'])
    assert _read(service, 'S1') == (None, None, None)


def test_desired_1459_leaves_confirmed_and_in_flight_none():
    sim, service = _connected(2, ['S1'])
    sim.issue_desired_price('S1', 1.459)
    assert _read(service, 'S1') == (1.459, None, None)


def test_desired_1479_replaces_desired_and_keeps_others_none():
    sim, service = _connected(3, ['S1'])
    sim.issue_desired_price('S1', 1.459)
    assert _read(service, 'S1') == (1.459, None, None)
    sim.issue_desired_price('S1', 1.479)
    assert _read(service, 'S1') == (1.479, None, None)


def test_second_station_starts_with_none_values():
    sim, service = _connected(4, ['S1', 'S2'])
    sim.issue_desired_price('S1', 1.459)
    sim.issue_desired_price('S1', 1.479)
    assert _read(service, 'S1') == (1.479, None, None)
    assert _read(service, 'S2') == (None, None, None)


def test_criterion_sequence_holds_for_several_seeds():
    for seed in range(1, 6):
        sim, service = _connected(seed, ['A', 'B'])
        assert _read(service, 'A') == (None, None, None)
        sim.issue_desired_price('A', 1.459)
        assert _read(service, 'A') == (1.459, None, None)
        sim.issue_desired_price('A', 1.479)
        assert _read(service, 'A') == (1.479, None, None)
        assert _read(service, 'B') == (None, None, None)
