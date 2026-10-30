import pytest

import app
import nrvv_env


def _setup(seed):
    sim = nrvv_env.Simulation(seed=seed)
    sim.connect(app)
    return sim


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_versions_increase_and_latest_price_supersedes(seed):
    sim = _setup(seed)
    prices = [10.0, 11.5, 9.25]
    versions = []
    for i, p in enumerate(prices):
        sim.advance(1)
        uid = sim.submit("A", p)
        assert uid is not None
        st = app.get_station_state("A")
        assert st["latest_desired_price"] == p
        versions.append(st["latest_version"])
        if i > 0:
            assert versions[i] > versions[i - 1]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_second_station_unaffected_by_first_station_submissions(seed):
    sim = _setup(seed)
    sim.advance(1)
    uid_b = sim.submit("B", 7.0)
    assert uid_b is not None
    before = app.get_station_state("B")
    assert before["latest_desired_price"] == 7.0
    for p in (10.0, 11.0, 12.0):
        sim.advance(1)
        assert sim.submit("A", p) is not None
        st_b = app.get_station_state("B")
        assert st_b["latest_desired_price"] == 7.0
        assert st_b["latest_version"] == before["latest_version"]
        assert app.get_station_state("A")["latest_desired_price"] == p


def test_interleaved_submissions_each_station_tracks_own_record():
    sim = _setup(5)
    seen = {"A": [], "B": []}
    plan = [("A", 1.0), ("B", 2.0), ("A", 3.0), ("B", 4.0), ("A", 5.0)]
    for sid, p in plan:
        sim.advance(1)
        assert sim.submit(sid, p) is not None
        for s in ("A", "B"):
            st = app.get_station_state(s)
            seen[s].append((st["latest_desired_price"], st["latest_version"]))
        assert app.get_station_state(sid)["latest_desired_price"] == p
    for s in ("A", "B"):
        vs = []
        for v in [x[1] for x in seen[s]]:
            if not vs or vs[-1] != v:
                vs.append(v)
        assert vs == sorted(vs) and len(set(vs)) == len(vs)
    assert app.get_station_state("A")["latest_desired_price"] == 5.0
    assert app.get_station_state("B")["latest_desired_price"] == 4.0
