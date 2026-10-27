import pytest
import app
import nrvv_env

STATION = "S1"
PRICES = [101, 102, 103]


def _make(seed=0):
    sim = nrvv_env.Simulation(seed=seed, station_ids=(STATION,))
    sim.connect(app)
    return sim


def _get(obj, names):
    for n in names:
        if isinstance(obj, dict) and n in obj:
            return True, obj[n]
        if hasattr(obj, n):
            return True, getattr(obj, n)
    return False, None


def _state():
    return app.get_station_state(STATION)


def _desired_price(state):
    ok, v = _get(state, ["latest_desired_price", "desired_price", "latestDesiredPrice", "price"])
    if ok:
        return v
    if isinstance(state, (tuple, list)) and state:
        return state[0]
    pytest.skip("precondition not reached: desired price not readable from station state")


def _version(state):
    ok, v = _get(state, ["desired_version", "version", "target_version", "latest_desired_version"])
    if ok:
        return v
    pytest.skip("precondition not reached: desired-price version not observable")


def _accepted(res):
    return res is True or (isinstance(res, str) and res.lower() == "accepted") or \
        (res is not None and res is not False and not (isinstance(res, str) and res.lower() == "rejected"))


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_record_holds_latest_submitted_price(seed):
    sim = _make(seed)
    for p in PRICES:
        res = sim.submit(STATION, p)
        assert _accepted(res)
        assert _desired_price(_state()) == p


def test_version_rises_by_exactly_one_per_accepted_change():
    sim = _make(3)
    sim.submit(STATION, PRICES[0])
    v = _version(_state())
    for p in PRICES[1:]:
        res = sim.submit(STATION, p)
        assert _accepted(res)
        nv = _version(_state())
        assert nv == v + 1
        v = nv


def test_earlier_prices_not_retained_or_queued():
    sim = _make(4)
    for p in PRICES:
        sim.submit(STATION, p)
    assert _desired_price(_state()) == PRICES[-1]
    sim.run_until_idle()
    assert _desired_price(_state()) == PRICES[-1]
    assert sim.station_price(STATION) == PRICES[-1]


def test_record_and_version_survive_restart():
    sim = _make(5)
    for p in PRICES:
        sim.submit(STATION, p)
    before = _state()
    price_before = _desired_price(before)
    assert price_before == PRICES[-1]
    ver_before = _version(before)
    restart = getattr(app, "restart", None)
    if not callable(restart):
        pytest.skip("precondition not reached: no way to restart the service through nrvv_env")
    restart()
    sim.connect(app)
    after = _state()
    assert _desired_price(after) == PRICES[-1]
    assert _version(after) == ver_before
