import pytest

import app
import nrvv_env


def _field(state, snake):
    parts = snake.split("_")
    camel = parts[0] + "".join(p.capitalize() for p in parts[1:])
    if isinstance(state, dict):
        for k in (snake, camel):
            if k in state:
                return state[k]
        raise AssertionError("state has no field %s: %r" % (snake, state))
    for k in (snake, camel):
        if hasattr(state, k):
            return getattr(state, k)
    if isinstance(state, (tuple, list)) and len(state) == 3:
        return state[("latest_desired_price", "last_acknowledged_price", "settled").index(snake)]
    raise AssertionError("state has no field %s: %r" % (snake, state))


def _check_settled(sim, station, last_price):
    state = app.get_station_state(station)
    assert _field(state, "settled") is True
    assert _field(state, "latest_desired_price") == last_price
    assert _field(state, "last_acknowledged_price") == last_price
    assert sim.station_price(station) == last_price


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_burst_during_in_flight_settles_on_last_price(seed):
    station = "burst-%d" % seed
    sim = nrvv_env.Simulation(seed=seed, station_ids=(station,), initial_price=100)
    sim.connect(app)
    sim.submit(station, 101)
    # newer prices while the first send is unacknowledged
    sim.submit(station, 102)
    sim.submit(station, 103)
    sim.step()
    sim.submit(station, 104)
    sim.submit(station, 105)
    sim.run_until_idle()
    _check_settled(sim, station, 105)


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_scheduled_submissions_with_reordering_settle(seed):
    station = "sched-%d" % seed
    sim = nrvv_env.Simulation(seed=seed, station_ids=(station,), initial_price=0)
    sim.connect(app)
    sim.submit(station, 10)
    for i, after in enumerate([0, 1, 1, 2, 3, 3, 5]):
        sim.schedule_submit(after, station, 20 + i)
    sim.run_until_idle()
    _check_settled(sim, station, 26)


def test_scripted_reverse_delivery_order_settles():
    station = "scripted-rev"
    sim = nrvv_env.Simulation(seed=7, station_ids=(station,), initial_price=0)
    sim.connect(app)
    sim.submit(station, 1)
    sim.submit(station, 2)
    sim.submit(station, 3)
    ids = [s.send_id for s in sim.sends if s.station_id == station]
    sim.set_delivery_order(station, list(reversed(ids)))
    sim.run_until_idle()
    _check_settled(sim, station, 3)


def test_scripted_order_with_late_submissions_settles():
    station = "scripted-late"
    sim = nrvv_env.Simulation(seed=21, station_ids=(station,), initial_price=0)
    sim.connect(app)
    sim.submit(station, 50)
    sim.submit(station, 51)
    ids = [s.send_id for s in sim.sends if s.station_id == station]
    sim.set_delivery_order(station, list(reversed(ids)))
    sim.schedule_submit(1, station, 52)
    sim.schedule_submit(2, station, 53)
    sim.run_until_idle()
    _check_settled(sim, station, 53)


def test_last_submitted_equals_earlier_price_still_settles():
    station = "same-as-earlier"
    sim = nrvv_env.Simulation(seed=5, station_ids=(station,), initial_price=0)
    sim.connect(app)
    sim.submit(station, 7)
    sim.submit(station, 8)
    sim.submit(station, 7)
    sim.run_until_idle()
    _check_settled(sim, station, 7)


@pytest.mark.parametrize("seed", [31, 32, 33])
def test_multiple_stations_each_settle_on_own_last_price(seed):
    stations = ["multi-%d-%d" % (seed, i) for i in range(3)]
    sim = nrvv_env.Simulation(seed=seed, station_ids=stations, initial_price=0)
    sim.connect(app)
    last = {}
    n = 100
    for round_ in range(4):
        for st in stations:
            n += 1
            sim.submit(st, n)
            last[st] = n
        sim.step()
        sim.step()
    for i, st in enumerate(stations):
        n += 1
        sim.schedule_submit(i, st, n)
        last[st] = n
    sim.run_until_idle()
    for st in stations:
        _check_settled(sim, st, last[st])


def test_manual_delivery_and_ack_by_send_id_settles():
    station = "manual"
    sim = nrvv_env.Simulation(seed=3, station_ids=(station,), initial_price=0)
    sim.connect(app)
    sim.submit(station, 1)
    sim.submit(station, 2)
    sim.submit(station, 3)
    guard = 0
    while sim.in_flight or sim.pending_acks:
        guard += 1
        assert guard < 1000
        if sim.pending_acks:
            sim.deliver_ack()
        else:
            # deliver the newest outstanding send first
            sim.deliver(sim.in_flight[-1].send_id)
    _check_settled(sim, station, 3)
