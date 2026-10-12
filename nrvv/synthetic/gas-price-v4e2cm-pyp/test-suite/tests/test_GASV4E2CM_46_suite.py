import random

from nrvv_env import Simulation

import app

SEEDS = (1, 2, 3, 4)


def _fields(status):
    if isinstance(status, dict):
        raw = status
    elif hasattr(status, '_asdict'):
        raw = status._asdict()
    else:
        raw = {name: getattr(status, name) for name in dir(status)
               if not name.startswith('_') and not callable(getattr(status, name))}
    return {str(key).lower(): value for key, value in raw.items()}


def _view(status):
    fields = _fields(status)
    desired = [v for k, v in fields.items() if 'desired' in k]
    confirmed = [v for k, v in fields.items() if 'confirmed' in k]
    flight = [(k, v) for k, v in fields.items() if 'flight' in k]
    price = [v for k, v in flight if not any(w in k for w in ('time', 'sent', 'at'))]
    when = [v for k, v in flight if any(w in k for w in ('time', 'sent', 'at'))]
    assert len(desired) == len(confirmed) == len(price) == len(when) == 1, sorted(fields)
    return desired[0], confirmed[0], price[0], when[0]


def _in_flight_price(sim, station_id):
    return _view(sim.status(station_id))[2]


def _accepted(result):
    if result is True:
        return True
    if isinstance(result, str):
        return result.strip().lower() == 'accepted'
    if isinstance(result, dict):
        return result.get('accepted') is True
    if hasattr(result, 'accepted'):
        return result.accepted is True
    name = getattr(result, 'name', None)
    return isinstance(name, str) and name.lower() == 'accepted'


def _snapshot(sim, station_id):
    _, confirmed, price, when = _view(sim.status(station_id))
    return {
        'now': sim.now,
        'sends': len(sim.sent),
        'deliveries': {s: len(st.received) for s, st in sim.stations.items()},
        'acks': len(sim.acks),
        'confirmed': confirmed,
        'flight': (price, when),
    }


def _assert_call_only_changes_record(before, after):
    assert after['now'] == before['now']
    assert after['sends'] == before['sends']
    assert after['deliveries'] == before['deliveries']
    assert after['acks'] == before['acks']
    assert after['confirmed'] == before['confirmed']
    assert after['flight'] == before['flight']


def test_set_desired_price_accepted_while_update_in_flight():
    for seed in SEEDS:
        sim = Simulation(app, seed, loss=0.0, outage=0.0)
        sim.set_desired_price('S1', 10)
        for _ in range(50):
            if _in_flight_price(sim, 'S1') is not None:
                break
            sim.tick()
        assert _in_flight_price(sim, 'S1') is not None
        before = _snapshot(sim, 'S1')
        result = sim.set_desired_price('S1', 20)
        assert _accepted(result), (seed, result)
        _assert_call_only_changes_record(before, _snapshot(sim, 'S1'))
        assert _view(sim.status('S1'))[0] == 20


def test_set_desired_price_accepted_when_no_update_in_flight():
    for seed in SEEDS:
        sim = Simulation(app, seed, loss=0.0, outage=0.0)
        assert _accepted(sim.set_desired_price('S1', 5))
        assert sim.quiesce()
        assert _in_flight_price(sim, 'S1') is None
        before = _snapshot(sim, 'S1')
        result = sim.set_desired_price('S1', 7)
        assert _accepted(result), (seed, result)
        _assert_call_only_changes_record(before, _snapshot(sim, 'S1'))
        assert _view(sim.status('S1'))[0] == 7


def test_set_desired_price_overwrites_without_blocking_over_seeded_schedule():
    saw_in_flight = False
    saw_idle = False
    for seed in SEEDS:
        sim = Simulation(app, seed)
        rng = random.Random(seed)
        for _ in range(120):
            if rng.random() < 0.4:
                station_id = rng.choice(sorted(sim.stations))
                price = rng.randrange(1, 100)
                in_flight = _in_flight_price(sim, station_id) is not None
                saw_in_flight = saw_in_flight or in_flight
                saw_idle = saw_idle or not in_flight
                before = _snapshot(sim, station_id)
                result = sim.set_desired_price(station_id, price)
                assert _accepted(result), (seed, station_id, price, result)
                _assert_call_only_changes_record(before, _snapshot(sim, station_id))
                assert _view(sim.status(station_id))[0] == price
            else:
                sim.tick()
    assert saw_in_flight and saw_idle
