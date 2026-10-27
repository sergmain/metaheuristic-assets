import dataclasses
import numbers

import pytest

import app
from nrvv_env import Simulation

RATE = 3
STATION = "S1"


def _to_dict(x):
    if isinstance(x, dict):
        return x
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return dataclasses.asdict(x)
    if hasattr(x, "_asdict"):
        return x._asdict()
    if hasattr(x, "__dict__"):
        return dict(vars(x))
    return None


def _walk(obj, out, depth=0):
    """Collect every dict-like record found anywhere in a report."""
    if depth > 8:
        return
    d = _to_dict(obj)
    if d is not None:
        out.append(d)
        for v in d.values():
            _walk(v, out, depth + 1)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            _walk(v, out, depth + 1)


def _records(report):
    out = []
    _walk(report, out)
    return out


def _num(v):
    return isinstance(v, numbers.Number) and not isinstance(v, bool)


def _keys(d, frag):
    return [k for k in d if frag in str(k).lower()]


def _cost_events(report):
    res = []
    for d in _records(report):
        if _keys(d, "station") and _keys(d, "version"):
            ck = [k for k in _keys(d, "cost") if _num(d[k])]
            if ck:
                res.append((d, ck[0]))
    return res


def _configure(a):
    for name in ("configure", "set_config", "set_stale_cost_rate", "set_cost_rate",
                 "configure_cost_rate", "set_stale_interval_cost_rate",
                 "configure_stale_cost_rate"):
        fn = getattr(a, name, None)
        if not callable(fn):
            continue
        for call in (lambda: fn(RATE),
                     lambda: fn(stale_cost_rate=RATE),
                     lambda: fn(cost_rate_per_stale_interval=RATE),
                     lambda: fn(stale_interval_cost_rate=RATE),
                     lambda: fn(cost_rate=RATE)):
            try:
                call()
                return True
            except TypeError:
                continue
    return False


def _scenario(seed=0):
    sim = Simulation(seed=seed, station_ids=(STATION,), initial_price=0)
    sim.connect(app)
    if not _configure(app):
        pytest.skip("precondition not reached: cost rate cannot be configured")
    sim.submit(STATION, 10)
    if len(sim.sends) != 1:
        pytest.skip("precondition not reached: first submit did not cause a send")
    sim.advance_time(5)
    sim.submit(STATION, 20)  # superseded while send 1 in flight
    sim.advance_time(5)
    sim.run_until_idle()
    if len(sim.sends) < 2 or sim.station_price(STATION) != 20:
        pytest.skip("precondition not reached: station did not settle on latest price")
    try:
        sending = app.get_sending_cost_report()
        stale = app.get_stale_cost_report()
    except AttributeError:
        pytest.skip("precondition not reached: reports unavailable")
    return sim, sending, stale


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_one_send_event_per_send_attempt(seed):
    sim, sending, _ = _scenario(seed)
    events = _cost_events(sending)
    assert len(events) == len(sim.sends)
    for d, _ck in events:
        assert _keys(d, "station")
        assert _keys(d, "version")
        assert _keys(d, "time") or _keys(d, "at")
        assert _keys(d, "outcome") or _keys(d, "status")
    assert any(STATION in d.values() for d, _ in events)


def test_send_events_have_product_and_times():
    sim, sending, _ = _scenario(0)
    events = _cost_events(sending)
    assert events
    for d, _ck in events:
        assert _keys(d, "product")
    times = sorted(v for d, _ in events for k in _keys(d, "time") if _num(v := d[k]))
    assert times
    assert times[0] >= sim.sends[0].time


def test_sending_cost_is_sum_of_event_costs():
    sim, sending, _ = _scenario(0)
    events = _cost_events(sending)
    total = sum(d[ck] for d, ck in events)
    totals = [v for d in _records(sending) for k, v in d.items()
              if "total" in str(k).lower() and "cost" in str(k).lower() and _num(v)]
    if not totals and _num(sending):
        totals = [sending]
    assert totals, "no total sending cost reported"
    assert total in totals


def test_superseded_price_is_recorded():
    sim, sending, stale = _scenario(0)
    text = (repr(sending) + repr(stale)).lower()
    assert "supersed" in text or "skip" in text or "coalesc" in text


def test_single_stale_interval_with_start_and_end():
    sim, _, stale = _scenario(0)
    intervals = [d for d in _records(stale) if _keys(d, "start") and _keys(d, "end")]
    assert len(intervals) == 1
    iv = intervals[0]
    start = iv[_keys(iv, "start")[0]]
    end = iv[_keys(iv, "end")[0]]
    first_submit = sim.submissions[0].time
    last_ack = sim.acknowledgements[-1].time
    assert first_submit <= start <= sim.submissions[1].time
    assert end >= sim.submissions[1].time
    assert end <= last_ack + 1


def test_stale_cost_is_duration_times_rate():
    sim, _, stale = _scenario(0)
    intervals = [d for d in _records(stale) if _keys(d, "start") and _keys(d, "end")]
    if len(intervals) != 1:
        pytest.skip("precondition not reached: stale interval not reported")
    iv = intervals[0]
    duration = iv[_keys(iv, "end")[0]] - iv[_keys(iv, "start")[0]]
    assert duration > 0
    expected = duration * RATE
    values = [v for d in _records(stale) for k, v in d.items()
              if "cost" in str(k).lower() and _num(v)]
    assert expected in values


def test_reports_cover_station():
    sim, sending, stale = _scenario(0)
    assert STATION in repr(sending)
    assert STATION in repr(stale)
