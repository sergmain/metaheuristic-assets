import inspect
import random

import app
import nrvv_env

STATION = 'station-46'
SEEDS = (1, 2, 3, 4, 5)
REFUSED = {'refused', 'rejected', 'deferred', 'queued', 'error', 'failed'}


def _read(state, name, index):
    if state is None:
        return None
    if isinstance(state, dict):
        for key, value in state.items():
            if name in str(key).lower():
                return value
        return None
    if hasattr(state, name):
        return getattr(state, name)
    return state[index]


def _build_service(sim):
    for _, cls in inspect.getmembers(app, inspect.isclass):
        if callable(getattr(cls, 'set_desired_price', None)):
            try:
                service = cls(sim.send_price_update)
            except TypeError:
                service = cls()
            return sim.connect(service)
    raise AssertionError('app has no class providing set_desired_price')


def _fresh(seed):
    sim = nrvv_env.Simulation(seed, [STATION], changes=0)
    return sim, _build_service(sim)


def _pair(seed):
    rng = random.Random(seed)
    first = rng.randint(1, 5)
    second = rng.choice([p for p in range(1, 6) if p != first])
    return first, second


def _assert_accepted(result):
    assert result is not False, 'second desired price was refused'
    if isinstance(result, str):
        assert result.lower() not in REFUSED, f'second desired price returned {result!r}'


def test_second_price_accepted_while_first_update_in_transit():
    for seed in SEEDS:
        sim, service = _fresh(seed)
        first, second = _pair(seed)
        service.set_desired_price(STATION, first)
        assert sim.outstanding(STATION) == 1
        result = service.set_desired_price(STATION, second)
        _assert_accepted(result)


def test_second_price_accepted_after_first_delivered_but_unacknowledged():
    for seed in SEEDS:
        sim, service = _fresh(seed)
        first, second = _pair(seed)
        service.set_desired_price(STATION, first)
        for _ in range(50):
            if sim.deliveries:
                break
            sim.step()
        assert sim.deliveries, 'first update was never delivered'
        assert sim.outstanding(STATION) == 1, 'first update was acknowledged too early'
        result = service.set_desired_price(STATION, second)
        _assert_accepted(result)


def test_second_price_stored_as_desired_immediately():
    for seed in SEEDS:
        sim, service = _fresh(seed)
        first, second = _pair(seed)
        service.set_desired_price(STATION, first)
        service.set_desired_price(STATION, second)
        state = service.inspect_station(STATION)
        assert _read(state, 'desired', 0) == second


def test_second_price_reaches_station_once_first_is_acknowledged():
    for seed in SEEDS:
        sim, service = _fresh(seed)
        first, second = _pair(seed)
        service.set_desired_price(STATION, first)
        service.set_desired_price(STATION, second)
        sim.run()
        assert sim.displayed(STATION) == second
        state = service.inspect_station(STATION)
        assert _read(state, 'confirmed', 1) == second
        assert _read(state, 'desired', 0) == second
        assert sim.outstanding(STATION) == 0
