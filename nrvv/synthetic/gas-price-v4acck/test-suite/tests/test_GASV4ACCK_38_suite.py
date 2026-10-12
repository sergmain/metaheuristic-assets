import dataclasses

import app
from nrvv_env import Simulation

SEEDS = range(25)
STATION = 'station-1'
CONFIRM_LIMIT = 120
MAX_TRANSPORT = 60


def _make_server():
    server_types = [
        value for value in vars(app).values()
        if isinstance(value, type) and hasattr(value, 'set_latest_price') and hasattr(value, 'tick')
    ]
    assert server_types, 'app defines no server class with set_latest_price and tick'
    return server_types[0]()


def _view_fields(view):
    if isinstance(view, dict):
        return list(view.values())
    if dataclasses.is_dataclass(view):
        return [getattr(view, f.name) for f in dataclasses.fields(view)]
    if isinstance(view, tuple):
        return list(view)
    return list(vars(view).values())


def _last_acknowledged(view):
    # GetStationView order: latest price, last-acknowledged price, outstanding price, change time
    return _view_fields(view)[1]


def _run_single_change(seed):
    sim = Simulation(seed, [STATION], changes_per_station=(1, 1))
    server = sim.bind(_make_server())
    acknowledged = {}
    for _ in range(sim.end_time + 1):
        t = sim.step()
        acknowledged[t] = _last_acknowledged(server.get_station_view(STATION))
    while sim.in_flight:
        t = sim.step()
        acknowledged[t] = _last_acknowledged(server.get_station_view(STATION))
    return sim, acknowledged


def test_new_price_is_sent_once_at_the_moment_of_change():
    for seed in SEEDS:
        sim, _ = _run_single_change(seed)
        (change,) = sim.changes
        assert len(sim.sends) == 1
        (record,) = sim.sends
        assert record.station == STATION
        assert record.price == change.price
        assert record.sent_at == change.time


def test_new_price_is_confirmed_at_acknowledgement_within_two_minutes():
    for seed in SEEDS:
        sim, acknowledged = _run_single_change(seed)
        (change,) = sim.changes
        (record,) = sim.sends
        assert record.acknowledged_at is not None
        ack_at = record.acknowledged_at
        assert record.delivered_at - record.sent_at <= MAX_TRANSPORT
        assert ack_at - record.delivered_at <= MAX_TRANSPORT
        assert ack_at <= change.time + CONFIRM_LIMIT
        for t, confirmed in acknowledged.items():
            if t < ack_at:
                assert confirmed != change.price
        assert acknowledged[ack_at] == change.price
