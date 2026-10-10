"""Tests for GASV4RDF1-55: show the pricing team the stations not yet acknowledging their latest price."""
import app
from nrvv_env import Simulation

SEEDS = (1, 7, 42)
DELAYS = ((0, 0), (0, 5), (1, 30))


def _sim(seed, delays=(0, 5)):
    return Simulation(seed, app, min_delay=delays[0], max_delay=delays[1])


def _ids(result):
    ids = set()
    for item in result:
        if isinstance(item, str):
            ids.add(item)
        elif isinstance(item, dict):
            ids.add(item["station_id"])
        else:
            ids.add(item.station_id)
    return ids


def test_station_without_acknowledgement_is_listed():
    for seed in SEEDS:
        sim = _sim(seed)
        sid = f"noack-{seed}"
        sim.add_station(sid)
        sim.set_desired_price(sid, 100)
        sim.run_until_idle()
        assert sid in _ids(sim.list_unacknowledged())


def test_station_acknowledging_same_price_is_omitted():
    for seed in SEEDS:
        sim = _sim(seed)
        sid = f"same-{seed}"
        sim.add_station(sid)
        sim.set_desired_price(sid, 100)
        sim.acknowledge(sid)
        sim.run_until_idle()
        assert sid not in _ids(sim.list_unacknowledged())


def test_station_acknowledging_older_price_is_listed():
    for seed in SEEDS:
        sim = _sim(seed)
        sid = f"older-{seed}"
        sim.add_station(sid)
        sim.set_desired_price(sid, 10)
        sim.acknowledge(sid)
        sim.run_until_idle()
        sim.set_desired_price(sid, 12)
        sim.run_until_idle()
        assert sid in _ids(sim.list_unacknowledged())


def test_acknowledging_latest_price_removes_station():
    for seed in SEEDS:
        sim = _sim(seed)
        sid = f"removed-{seed}"
        sim.add_station(sid)
        sim.set_desired_price(sid, 10)
        sim.acknowledge(sid)
        sim.run_until_idle()
        sim.set_desired_price(sid, 12)
        sim.run_until_idle()
        assert sid in _ids(sim.list_unacknowledged())
        sim.acknowledge(sid)
        sim.run_until_idle()
        assert sid not in _ids(sim.list_unacknowledged())


def test_most_recent_acknowledgement_decides():
    for seed in SEEDS:
        sim = _sim(seed)
        sid = f"recent-{seed}"
        sim.add_station(sid)
        sim.set_desired_price(sid, 10)
        sim.acknowledge(sid)
        sim.run_until_idle()
        sim.set_desired_price(sid, 12)
        sim.acknowledge(sid)
        sim.run_until_idle()
        assert sid not in _ids(sim.list_unacknowledged())
        sim.set_desired_price(sid, 13)
        sim.run_until_idle()
        assert sid in _ids(sim.list_unacknowledged())


def test_listing_is_exactly_the_unacknowledged_stations():
    for seed in SEEDS:
        for delays in DELAYS:
            sim = _sim(seed, delays)
            p = f"mix-{seed}-{delays[1]}-"
            for name in ("never", "same", "stale", "fresh"):
                sim.add_station(p + name)
            sim.set_desired_price(p + "never", 10)
            sim.set_desired_price(p + "same", 20)
            sim.set_desired_price(p + "stale", 30)
            sim.set_desired_price(p + "fresh", 40)
            sim.acknowledge(p + "same")
            sim.acknowledge(p + "stale")
            sim.acknowledge(p + "fresh")
            sim.run_until_idle()
            sim.set_desired_price(p + "stale", 31)
            sim.run_until_idle()
            own = {s for s in _ids(sim.list_unacknowledged()) if s.startswith(p)}
            assert own == {p + "never", p + "stale"}


def test_listing_changes_no_state():
    for seed in SEEDS:
        sim = _sim(seed)
        sid = f"ro-{seed}"
        sim.add_station(sid)
        sim.set_desired_price(sid, 5)
        sim.run_until_idle()
        traffic_before = len(sim.traffic)
        first = _ids(sim.list_unacknowledged())
        second = _ids(sim.list_unacknowledged())
        assert first == second
        assert sid in first
        assert len(sim.traffic) == traffic_before
        assert sim.in_flight() == []
        assert sim.notices == []
