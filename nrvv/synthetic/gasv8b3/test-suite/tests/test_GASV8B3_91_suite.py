import pytest

import app
import nrvv_env


def _numbers(obj, out=None):
    if out is None:
        out = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            _numbers(v, out)
    elif hasattr(obj, "__dict__"):
        _numbers(vars(obj), out)
    return out


def _setup(seed, station):
    sim = nrvv_env.Simulation(seed=seed, station_ids=(station,))
    sim.connect(app)
    return sim


def _coalesced_scenario(seed, station, prices):
    sim = _setup(seed, station)
    sim.submit(station, prices[0])
    for p in prices[1:]:
        sim.advance_time(3)
        sim.submit(station, p)
    sim.advance_time(3)
    sim.run_until_idle()
    sent = [r.price for r in sim.sends]
    if all(p in sent for p in prices):
        pytest.skip("precondition not reached: some price was not withheld/superseded")
    return sim


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_stale_cost_nonzero_when_newer_price_replaces_unsent(seed):
    st = "st-coalesce-%d" % seed
    _coalesced_scenario(seed, st, [101, 102, 103])
    report = app.get_stale_cost_report()
    assert report
    nums = _numbers(report)
    assert nums and max(nums) > 0


@pytest.mark.parametrize("seed", [4, 5])
def test_stale_report_names_station_with_unsent_price(seed):
    st = "st-named-%d" % seed
    _coalesced_scenario(seed, st, [201, 202, 203, 204])
    report = app.get_stale_cost_report()
    assert st in repr(report) or st in str(report)
    assert max(_numbers(report) or [0]) > 0


def test_stale_cost_zero_when_every_price_sent():
    st = "st-allsent"
    sim = _setup(7, st)
    sim.submit(st, 301)
    sim.run_until_idle()
    if [r.price for r in sim.sends] != [301]:
        pytest.skip("precondition not reached: single price not sent exactly once")
    report = app.get_stale_cost_report()
    nums = _numbers(report)
    assert all(n == 0 for n in nums)


def test_stale_cost_zero_when_sequential_prices_all_sent():
    st = "st-seq"
    sim = _setup(8, st)
    prices = [401, 402, 403]
    for p in prices:
        sim.submit(st, p)
        sim.run_until_idle()
        sim.advance_time(2)
    if [r.price for r in sim.sends] != prices:
        pytest.skip("precondition not reached: all prices sent individually")
    report = app.get_stale_cost_report()
    assert all(n == 0 for n in _numbers(report))
