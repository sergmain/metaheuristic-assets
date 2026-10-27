import pytest

import app
import nrvv_env

DESIRED_NAMES = ("latest_desired_price", "desired_price", "target_price", "price")
VERSION_NAMES = ("version", "desired_version", "target_version", "latest_version")


def _field(rec, names):
    if rec is None:
        return None
    if isinstance(rec, dict):
        for n in names:
            if n in rec:
                return rec[n]
        return None
    for n in names:
        if hasattr(rec, n):
            return getattr(rec, n)
    return None


def _desired(sid):
    st = app.get_station_state(sid)
    if isinstance(st, (tuple, list)) and not hasattr(st, "_fields"):
        return st[0]
    if hasattr(st, "_fields") and not hasattr(st, "latest_desired_price"):
        return st[0]
    return _field(st, DESIRED_NAMES)


def _version(sid):
    for fn_name in ("get_station_state", "get_station_record", "get_desired_record"):
        fn = getattr(app, fn_name, None)
        if not callable(fn):
            continue
        try:
            v = _field(fn(sid), VERSION_NAMES)
        except Exception:
            continue
        if v is not None:
            return v
    return None


def _make(seed, stations):
    sim = nrvv_env.Simulation(seed=seed, station_ids=stations, initial_price=0)
    sim.connect(app)
    return sim


PRICES = (1501, 1602, 1703)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_desired_price_is_only_latest_after_each_submit(seed):
    sim = _make(seed, ["A", "B"])
    for p in PRICES:
        sim.submit("A", p)
        assert _desired("A") == p


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_versions_strictly_increase_by_one_per_accepted_price(seed):
    sim = _make(seed, ["A"])
    versions = []
    for p in PRICES:
        sim.submit("A", p)
        v = _version("A")
        if v is None:
            pytest.skip("precondition not reached: version not observable in station record")
        versions.append(v)
    assert versions[0] < versions[1] < versions[2]
    assert versions[1] == versions[0] + 1
    assert versions[2] == versions[1] + 1


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_other_station_version_unchanged(seed):
    sim = _make(seed, ["A", "B"])
    sim.submit("B", 1999)
    vb = _version("B")
    if vb is None:
        pytest.skip("precondition not reached: version not observable in station record")
    for p in PRICES:
        sim.submit("A", p)
        assert _version("B") == vb
        assert _desired("B") == 1999


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_older_prices_never_reappear_with_late_acks(seed):
    sim = _make(seed, ["A"])
    sim.submit("A", PRICES[0])
    sim.submit("A", PRICES[1])
    assert _desired("A") == PRICES[1]
    sim.submit("A", PRICES[2])
    assert _desired("A") == PRICES[2]
    n = 0
    while sim.step():
        assert _desired("A") == PRICES[2]
        n += 1
        assert n < 10000
    assert _desired("A") == PRICES[2]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_late_ack_for_older_send_does_not_change_version(seed):
    sim = _make(seed, ["A"])
    sim.submit("A", PRICES[0])
    first_sends = list(sim.sends)
    if not first_sends:
        pytest.skip("precondition not reached: no send dispatched on submit")
    old = first_sends[0]
    sim.submit("A", PRICES[1])
    sim.submit("A", PRICES[2])
    v_before = _version("A")
    sim.deliver(old.send_id)
    sim.deliver_ack()
    assert _desired("A") == PRICES[2]
    if v_before is not None:
        assert _version("A") == v_before
    sim.run_until_idle()
    assert _desired("A") == PRICES[2]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_no_version_sent_to_station(seed):
    sim = _make(seed, ["A", "B"])
    for p in PRICES:
        sim.submit("A", p)
    sim.submit("B", 1888)
    sim.run_until_idle()
    allowed = set(PRICES) | {1888}
    assert sim.sends
    for s in sim.sends:
        assert s.price in allowed
        assert isinstance(s.price, (int, float))
    # the station ends on the latest price; nothing but prices was applied
    assert sim.station_price("A") == PRICES[2]
    assert sim.station_price("B") == 1888
