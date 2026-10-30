import re

import pytest

import app
import nrvv_env

T0 = 100.0
RATE = 2.0
SEND_COST = 7.0


def _norm(key):
    return re.sub(r"[^a-z]", "", str(key).lower())


def _walk(obj, path=()):
    """Yield (path_of_normalised_keys, number) for every numeric leaf."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield path, float(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, path + (_norm(k),))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk(v, path)


def _values(report, *needles):
    out = []
    for path, num in _walk(report):
        if any(any(n in p for n in needles) for p in path):
            out.append(num)
    return out


def _get_report(period_end):
    candidates = [(T0, period_end), {"start": T0, "end": period_end}, None]
    last = None
    for p in candidates:
        try:
            return app.get_stale_price_cost_report(p)
        except Exception as exc:  # period format unknown
            last = exc
    raise last


def _scenario(seed, station="S1", price=5.0):
    sim = nrvv_env.Simulation(seed=seed, cost_per_send=SEND_COST,
                              stale_cost_per_time=RATE, start_time=T0,
                              ordering="fifo")
    sim.connect(app)
    # desired at T0, but the first send is issued at T0+10
    sim.set_time(T0 + 10)
    app.submit_price_update(station, price, T0)
    if not sim.sends or sim.sends[0]["time"] != T0 + 10:
        pytest.skip("precondition not reached: first send issued at T0+10")
    sim.set_time(T0 + 25)
    sim.run_until_idle()
    if not sim.acknowledgements:
        pytest.skip("precondition not reached: acknowledgement delivered")
    return sim


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_stale_cost_split_into_not_sent_and_unconfirmed(seed):
    _scenario(seed)
    report = _get_report(T0 + 25)
    not_sent = _values(report, "notsent", "unsent")
    in_flight = _values(report, "unconfirmed", "inflight")
    if not not_sent or not in_flight:
        pytest.fail("report lacks not-sent / sent-but-unconfirmed breakdown: %r" % (report,))
    assert RATE * 10 in not_sent
    assert RATE * 15 in in_flight


@pytest.mark.parametrize("seed", [1, 2])
def test_parts_sum_to_total_without_send_cost(seed):
    _scenario(seed)
    report = _get_report(T0 + 25)
    total = RATE * 25
    assert report["cost_total"] == pytest.approx(total)
    not_sent = _values(report, "notsent", "unsent")
    in_flight = _values(report, "unconfirmed", "inflight")
    assert RATE * 10 in not_sent and RATE * 15 in in_flight
    assert RATE * 10 + RATE * 15 == pytest.approx(report["cost_total"])
    # send cost (7 per send) must not be part of any figure
    for _, num in _walk(report):
        assert num != pytest.approx(total + SEND_COST)
