"""Requirement GASV4ACCJ-16: earliest next send is 60 seconds after the previous send."""

import importlib

from nrvv_env import Simulation

STATION = "S1"
SLOT = 60.0
HORIZON_END = 2400.0
SEEDS = (1, 2, 3, 4, 5)


def _simulation(seed):
    return Simulation(seed, stations=(STATION,), drop_probability=0.0)


def _fresh_app():
    import app
    return importlib.reload(app)


def _find_seed(predicate, limit=20000):
    for seed in range(limit):
        if predicate(_simulation(seed)):
            return seed
    raise AssertionError("no seed in range gives the required price-change timing")


def _ack_run_seed(sim):
    times = [when for when, _, _ in sim.schedule()]
    if len(times) < 3:
        return False
    t0 = times[0]
    inside = [t for t in times if t0 < t < t0 + SLOT]
    return (sim.reachable(STATION, t0)
            and len(inside) == 2
            and t0 + 5 <= inside[0] <= t0 + 20
            and t0 + 35 <= inside[1] <= t0 + 55)


def _ack_run():
    seed = _find_seed(_ack_run_seed)
    sim = _simulation(seed)
    sim.connect(_fresh_app())
    return sim


def _abandon_run_seed(sim):
    times = [when for when, _, _ in sim.schedule()]
    if not times:
        return False
    t0 = times[0]
    return (not sim.reachable(STATION, t0)
            and any(t0 + 30 < t < t0 + SLOT for t in times))


def test_no_send_before_sixty_seconds_after_acknowledged_send():
    sim = _ack_run()
    t0 = sim.schedule()[0][0]
    sim.run_until(t0 + SLOT - 1e-6)
    assert any(a.station == STATION for a in sim.acks())
    assert [r.sent_at for r in sim.sends() if r.station == STATION] == [t0]


def test_single_send_at_sixty_seconds_carries_latest_price():
    sim = _ack_run()
    schedule = sim.schedule()
    t0 = schedule[0][0]
    latest_price = schedule[2][2]
    sim.run_until(t0 + SLOT)
    at_slot = [r for r in sim.sends() if r.station == STATION and r.sent_at == t0 + SLOT]
    assert len(at_slot) == 1
    assert at_slot[0].price == latest_price


def test_abandoned_send_still_holds_back_next_send_until_sixty_seconds():
    seed = _find_seed(_abandon_run_seed)
    sim = _simulation(seed)
    sim.connect(_fresh_app())
    t0 = sim.schedule()[0][0]
    sim.run_until(t0 + SLOT - 1e-6)
    first = sim.sends()[0]
    assert first.state == "dropped" and first.reason == "unreachable"
    assert not any(a.station == STATION for a in sim.acks())
    assert [r.sent_at for r in sim.sends() if r.station == STATION] == [t0]


def test_consecutive_sends_to_a_station_are_at_least_sixty_seconds_apart():
    for seed in SEEDS:
        sim = Simulation(seed)
        sim.connect(_fresh_app())
        sim.run_until(HORIZON_END)
        for station in sim.stations:
            sent = sorted(r.sent_at for r in sim.sends() if r.station == station)
            for earlier, later in zip(sent, sent[1:]):
                assert later - earlier >= SLOT - 1e-9, (seed, station, earlier, later)
