'''Tests for GASV4E2CL-17: the station only receives the update form and acknowledges it.'''
import pytest

import app
from nrvv_env import Simulation, message_form_violations

SEEDS = (1, 2, 3, 4, 5)
STATION = 'S1'
PRICE = 42
TRIGGER_AT = 10


def _new_server(send_price_update):
    for value in vars(app).values():
        if isinstance(value, type) and hasattr(value, 'set_desired_price'):
            try:
                return value(send_price_update)
            except TypeError:
                return value(send_price_update=send_price_update)
    pytest.fail('app defines no class with set_desired_price')


def _sim(seed):
    sim = Simulation(seed, _new_server, stations=(STATION,), duration=0)
    sim._push(TRIGGER_AT, 'price', (STATION, PRICE))   # one change from the central price source
    return sim


def test_single_trigger_sends_exactly_one_update_to_station():
    for seed in SEEDS:
        sim = _sim(seed)
        sim.run_until_idle()
        assert [m.station for m in sim.to_station] == [STATION]
        assert [m.kind for m in sim.to_station] == ['update']


def test_update_carries_exactly_price_and_update_identifier():
    for seed in SEEDS:
        sim = _sim(seed)
        sim.run_until_idle()
        (update,) = sim.to_station
        assert isinstance(update.update_id, int) and not isinstance(update.update_id, bool)
        assert update.price == PRICE
        assert sim.stations[STATION].received == [(update.update_id, PRICE)]
        assert len(sim.stations[STATION].received[0]) == 2


def test_no_query_reset_or_control_message_to_station():
    for seed in range(1, 21):
        sim = _sim(seed)
        sim.run_until_idle()
        assert message_form_violations(sim) == []
        assert all(m.kind == 'update' for m in sim.to_station)
        assert len(sim.to_station) == len(sim.sends)


def test_nothing_sent_after_station_acknowledges_update():
    for seed in SEEDS:
        sim = _sim(seed)
        acknowledged = False
        frozen = None
        while True:
            sent_before = len(sim.to_station)
            if not sim.step():
                break
            if frozen is not None:
                assert len(sim.to_station) == frozen, f'seed {seed}: message sent after acknowledgement'
            elif any(a.delivered_at is not None for a in sim.from_station):
                acknowledged = True
                assert len(sim.to_station) == sent_before, f'seed {seed}: message sent in response to acknowledgement'
                frozen = len(sim.to_station)
        assert acknowledged, f'seed {seed}: acknowledgement never delivered'
        assert len(sim.to_station) == 1


def test_acknowledgement_names_identifier_carried_by_update():
    for seed in SEEDS:
        sim = _sim(seed)
        sim.run_until_idle()
        (update,) = sim.to_station
        (ack,) = sim.from_station
        assert ack.kind == 'ack'
        assert ack.station == STATION
        assert ack.update_id == update.update_id
        assert ack.delivered_at is not None
