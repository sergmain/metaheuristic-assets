import importlib

import app
from nrvv_env import MAX_DELAY, Simulation

SEEDS = (1, 2, 3, 5, 8)
STATION = 'S1'
CHANGE = 'change'  # nrvv_env's kind for a scheduled SetLatestPrice


def _server():
    # reload gives each test a fresh server state
    return importlib.reload(app)


def _scripted(seed):
    sim = Simulation(seed, [STATION], changes_per_station=(1, 1))
    sim.bind(_server())
    sim._heap.clear()  # drop the seeded random schedule; each test scripts its own price changes
    return sim


def _set_price_now(sim, price):
    sim._push(sim.now, CHANGE, (STATION, price))


def test_no_update_when_latest_price_equals_acknowledged_price():
    for seed in SEEDS:
        sim = _scripted(seed)
        _set_price_now(sim, '100')
        sim.run_until_idle()
        assert [r.price for r in sim.sends] == ['100']
        assert sim.sends[0].acknowledged_at is not None
        baseline = sim.send_counts()[STATION]

        _set_price_now(sim, '100')
        sim.step()
        sim.run_until(sim.now + 2 * MAX_DELAY)

        assert sim.send_counts()[STATION] - baseline == 0


def test_new_price_sends_one_update_that_stays_unacknowledged_until_ack():
    for seed in SEEDS:
        sim = _scripted(seed)
        _set_price_now(sim, '100')
        sim.run_until_idle()
        baseline = sim.send_counts()[STATION]

        _set_price_now(sim, '120')
        sim.step()
        assert sim.send_counts()[STATION] - baseline == 1
        update = sim.sends[-1]
        assert update.price == '120'
        assert update.acknowledged_at is None

        sim.step()  # trigger the update process again while latest price is still 120
        assert sim.send_counts()[STATION] - baseline == 1

        sim.run_until_idle()
        assert sim.send_counts()[STATION] - baseline == 1
        assert sim.sends[-1].acknowledged_at is not None


def test_no_redundant_update_in_random_runs():
    for seed in range(20):
        sim = Simulation(seed, ['A', 'B', 'C'], price_range=(1, 3))
        sim.bind(_server())
        sim.run_to_end()
        for station in sim.stations:
            sends = [r for r in sim.sends if r.station == station]
            for i, r in enumerate(sends):
                acked_before = [q for q in sends[:i]
                                if q.acknowledged_at is not None and q.acknowledged_at < r.sent_at]
                if acked_before:
                    assert acked_before[-1].price != r.price
                outstanding = [q for q in sends[:i]
                               if q.acknowledged_at is None or q.acknowledged_at > r.sent_at]
                assert all(q.price != r.price for q in outstanding)
