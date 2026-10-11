"""GASV4ACCJ-34 suite: at most one price update per station per 60-second period (GASV4ACCJ-8)."""

import app
from nrvv_env import Simulation

PERIOD = 60.0
SEED_LIMIT = 5000


def _burst_plan():
    # Scan fixed seeds for a station whose schedule holds a burst of at least three
    # changes inside one 60 s period, whose latest burst price differs from every
    # earlier burst price, and which has exactly one later change at least 120 s after
    # the burst start.
    for seed in range(SEED_LIMIT):
        per_station = {}
        for when, station, price in Simulation(seed).schedule():
            per_station.setdefault(station, []).append((when, price))
        for station, changes in per_station.items():
            first = changes[0][0]
            burst = [c for c in changes if c[0] < first + PERIOD]
            rest = changes[len(burst):]
            if len(burst) < 3 or len(rest) != 1:
                continue
            burst_prices = [price for _, price in burst]
            if burst_prices[-1] in burst_prices[:-1]:
                continue
            if rest[0][0] < first + 2 * PERIOD:
                continue
            return {
                'seed': seed,
                'station': station,
                'start': first,
                'latest': burst_prices[-1],
                'later_at': rest[0][0],
                'later_price': rest[0][1],
            }
    raise AssertionError('no seed in range gives a burst followed by one later change')


def _run(seed):
    sim = Simulation(seed)
    sim.connect(app)
    horizon = max(when for when, _, _ in sim.schedule())
    sim.run_until(horizon + 300.0)
    sim.run_until_quiet()
    return sim


def test_burst_in_one_period_sends_single_update_with_latest_price():
    plan = _burst_plan()
    station = plan['station']
    start = plan['start']
    sim = Simulation(plan['seed'])
    sim.connect(app)

    sim.run_until(start + PERIOD)
    period_sends = [
        s for s in sim.sends()
        if s.station == station and start <= s.sent_at <= start + PERIOD
    ]
    assert len(period_sends) == 1, f'expected one update in the period, got {len(period_sends)}'
    assert period_sends[0].price == plan['latest'], (
        f'update sent price {period_sends[0].price}, latest desired is {plan["latest"]}')

    sim.run_until(plan['later_at'] + 300.0)
    sim.run_until_quiet()
    later = [s for s in sim.sends() if s.station == station and s.sent_at > start + PERIOD]
    assert len(later) == 1, f'expected one update after the period, got {len(later)}'
    assert later[0].price == plan['later_price'], (
        f'later update sent price {later[0].price}, expected {plan["later_price"]}')


def test_consecutive_sends_to_a_station_are_at_least_60_seconds_apart():
    for seed in range(10):
        sim = _run(seed)
        by_station = {}
        for s in sim.sends():
            by_station.setdefault(s.station, []).append(s.sent_at)
        for station, times in by_station.items():
            times.sort()
            for earlier, later in zip(times, times[1:]):
                assert later - earlier >= PERIOD, (
                    f'seed {seed}: station {station} sent at {earlier} and {later}')


def test_sent_prices_are_prices_desired_for_that_station():
    for seed in range(5):
        sim = _run(seed)
        desired = {}
        for _, station, price in sim.schedule():
            desired.setdefault(station, set()).add(price)
        for s in sim.sends():
            assert s.price in desired[s.station], (
                f'seed {seed}: sent price {s.price} to {s.station} was never desired')
