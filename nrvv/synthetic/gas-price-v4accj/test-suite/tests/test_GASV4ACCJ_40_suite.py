import app
from nrvv_env import Simulation

STATION = 'S1'
SEEDS = range(40)


def _loss_rate(seed):
    return (0.1, 0.3, 0.6)[seed % 3]


def _run(seed, first, second, gap):
    # horizon=0 leaves the environment's own price-change schedule empty, so the
    # only changes are the two set below; the environment still delays, loses and
    # reorders the sends the service makes.
    sim = Simulation(seed, app, station_ids=(STATION,), horizon=0, loss_rate=_loss_rate(seed))
    sim.server.set_desired_price(STATION, first)
    sim.advance_to(gap)
    sim.server.set_desired_price(STATION, second)
    sim.run_until_idle()
    return sim


def test_applied_price_is_latest_desired_price_without_station_versioning():
    for seed in SEEDS:
        first, second = 60 + seed, 120 + seed
        sim = _run(seed, first, second, gap=1 + seed % 5)
        assert sim.applied_price(STATION) == second, 'seed %d' % seed


def test_applied_price_stays_latest_once_service_has_settled():
    for seed in SEEDS:
        first, second = 60 + seed, 120 + seed
        sim = _run(seed, first, second, gap=1 + seed % 5)
        deliveries_before = len(sim.stations[STATION].deliveries)
        sim.advance_to(sim.now + 300)
        assert sim.applied_price(STATION) == second, 'seed %d' % seed
        assert len(sim.stations[STATION].deliveries) == deliveries_before, 'seed %d' % seed


def test_stale_update_delivered_after_latest_still_leaves_latest_price():
    stale_seen = 0
    for seed in SEEDS:
        first, second = 60 + seed, 120 + seed
        sim = _run(seed, first, second, gap=1)
        deliveries = sim.stations[STATION].deliveries
        first_second = next((i for i, d in enumerate(deliveries) if d.price == second), None)
        if first_second is None:
            continue
        if any(d.price == first for d in deliveries[first_second + 1:]):
            stale_seen += 1
            assert sim.applied_price(STATION) == second, 'seed %d' % seed
    assert stale_seen > 0
