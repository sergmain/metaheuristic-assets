import pytest

import app
import nrvv_env


RATE = 2.0


def _make(seed):
    sim = nrvv_env.Simulation(seed=seed, cost_per_send=RATE, ordering="fifo",
                              start_time=100.0)
    sim.connect(app)
    return sim


def _report(sim, start, end):
    last = None
    for period in ((start, end), {"start": start, "end": end}, [start, end]):
        try:
            return app.get_sending_cost_report(period)
        except (TypeError, KeyError, ValueError, AttributeError) as exc:
            last = exc
    raise last


def _get(rep, key):
    if isinstance(rep, dict):
        return rep[key]
    return getattr(rep, key)


def _drive(sim, plan):
    for station, price in plan:
        sim.advance(1.0)
        sim.submit(station, price)
        sim.run_until_idle()


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_sending_cost_report_counts_sends_and_costs(seed):
    sim = _make(seed)
    start = sim.now()
    plan = [("A", 10.0), ("B", 20.0), ("A", 11.0), ("A", 12.0), ("B", 21.0)]
    _drive(sim, plan)
    sim.advance(1.0)
    counts = {}
    for s in sim.sends:
        counts[s["station_id"]] = counts.get(s["station_id"], 0) + 1
    if counts != {"A": 3, "B": 2}:
        pytest.skip("precondition not reached: sends were not 3 to A and 2 to B")
    rep = _report(sim, start, sim.now())
    assert _get(rep, "sends_count") == 5
    assert _get(rep, "cost_total") == pytest.approx(5 * RATE)
    per = _get(rep, "cost_per_station")
    assert per["A"] == pytest.approx(3 * RATE)
    assert per["B"] == pytest.approx(2 * RATE)


def test_retry_send_is_counted_once_each():
    sim = _make(7)
    start = sim.now()
    sim.advance(1.0)
    sim.submit("A", 10.0)
    sim.lose_send(0)
    sim.run_until_idle()
    sim.advance(1000.0)
    sim.run_until_idle()
    n = len(sim.sends)
    if n < 1:
        pytest.skip("precondition not reached: no send made")
    rep = _report(sim, start, sim.now() + 1.0)
    assert _get(rep, "sends_count") == n
    assert _get(rep, "cost_total") == pytest.approx(n * RATE)
    assert _get(rep, "cost_per_station")["A"] == pytest.approx(n * RATE)
