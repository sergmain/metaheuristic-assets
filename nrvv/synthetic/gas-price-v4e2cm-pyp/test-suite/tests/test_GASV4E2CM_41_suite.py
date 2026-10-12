'''Tests for GASV4E2CM-3: a new desired price is accepted while earlier updates are unacknowledged.'''
import app
from nrvv_env import Simulation

PRICE_FIRST = 10
PRICE_NEW = 20
SEEDS = (1, 2, 3, 4, 5)


def _field(status, *names):
    for name in names:
        if isinstance(status, dict) and name in status:
            return status[name]
        if hasattr(status, name):
            return getattr(status, name)
    raise AssertionError(f'status has none of the fields {names}: {status!r}')


def _assert_accepted(result):
    if isinstance(result, bool):
        assert result is True
        return
    assert result is not None
    text = repr(result).lower()
    assert 'reject' not in text and 'delay' not in text, result


def _silent_station_sim(seed, station_id):
    sim = Simulation(app, seed, stations=(station_id,), loss=0.0, outage=0.0)
    sim.stations[station_id].outages.append((0, 10 ** 6))
    return sim


def test_new_desired_price_accepted_while_earlier_update_unacknowledged():
    for seed in SEEDS:
        station_id = f'OUT-{seed}'
        sim = _silent_station_sim(seed, station_id)
        sim.set_desired_price(station_id, PRICE_FIRST)
        sim.tick()
        assert [entry['price'] for entry in sim.sent_to(station_id)] == [PRICE_FIRST]
        assert sim.acks == []
        result = sim.set_desired_price(station_id, PRICE_NEW)
        _assert_accepted(result)
        assert _field(sim.status(station_id), 'desired_price', 'desired') == PRICE_NEW


def test_new_desired_price_accepted_without_earlier_update():
    for seed in SEEDS:
        station_id = f'IDLE-{seed}'
        sim = _silent_station_sim(seed, station_id)
        result = sim.set_desired_price(station_id, PRICE_NEW)
        _assert_accepted(result)
        assert _field(sim.status(station_id), 'desired_price', 'desired') == PRICE_NEW
