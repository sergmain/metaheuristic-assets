'''Tests for GASV4E2CM-8: the service records each station's latest confirmed price.'''

import inspect

import pytest

import app
from nrvv_env import Simulation
from nrvv_env.simulation import _status_fields

SEEDS = (1, 2, 3, 4, 5)
SERVICE_OPERATIONS = ('set_desired_price', 'get_station_status', 'clock_tick')


def _make_service():
    if all(callable(getattr(app, name, None)) for name in SERVICE_OPERATIONS):
        return app
    for name in sorted(dir(app)):
        candidate = getattr(app, name)
        if inspect.isclass(candidate) and all(callable(getattr(candidate, op, None)) for op in SERVICE_OPERATIONS):
            return candidate()
    pytest.fail('app exposes no service with set_desired_price, get_station_status and clock_tick')


def _new_simulation(seed):
    # No loss and no outages: every update is delivered and acknowledged, in sending order.
    return Simulation(_make_service(), seed, ['A', 'B'], loss=0.0, max_outages_per_station=0)


def _confirmed_price(sim, station_id):
    return _status_fields(sim.get_station_status(station_id))[1]


def _acked_prices(sim, station_id):
    return [ack.price for ack in sim.acks if ack.station == station_id]


def _confirm_two_prices_for_a(seed):
    sim = _new_simulation(seed)
    sim.set_desired_price('A', '1.50')
    sim.quiesce()
    sim.set_desired_price('A', '1.60')
    sim.quiesce()
    assert _acked_prices(sim, 'A') == ['1.50', '1.60'], 'seed %d: station A acknowledgements' % seed
    return sim


def _confirm_single_price_for_b(sim, seed):
    sim.set_desired_price('B', '2.10')
    sim.quiesce()
    assert _acked_prices(sim, 'B') == ['2.10'], 'seed %d: station B acknowledgements' % seed


def test_latest_ack_overrides_earlier_ack_for_station_a():
    for seed in SEEDS:
        sim = _confirm_two_prices_for_a(seed)
        assert _confirmed_price(sim, 'A') == '1.60', 'seed %d' % seed


def test_station_b_records_its_single_ack_price():
    for seed in SEEDS:
        sim = _new_simulation(seed)
        _confirm_single_price_for_b(sim, seed)
        assert _confirmed_price(sim, 'B') == '2.10', 'seed %d' % seed


def test_station_a_keeps_1_60_after_station_b_ack():
    for seed in SEEDS:
        sim = _confirm_two_prices_for_a(seed)
        assert _confirmed_price(sim, 'A') == '1.60', 'seed %d' % seed
        _confirm_single_price_for_b(sim, seed)
        assert _confirmed_price(sim, 'B') == '2.10', 'seed %d' % seed
        assert _confirmed_price(sim, 'A') == '1.60', 'seed %d' % seed
