from nrvv_env import Simulation, StationClient
import app

SEEDS = (1, 2, 3, 5, 8)
STATION = 'S1'


def _make_server():
    candidates = [v for v in vars(app).values()
                  if isinstance(v, type) and callable(getattr(v, 'set_latest_price', None))]
    assert candidates, 'app must provide a class with set_latest_price'
    return candidates[0]()


def _run_busy_then_superseded(seed):
    sim = Simulation(seed, stations=[])
    sim.stations[STATION] = StationClient(STATION)
    server = sim.bind(_make_server())
    server.set_latest_price(STATION, 'X')  # makes the station busy at time 0
    server.set_latest_price(STATION, 'A')  # pending while busy
    server.set_latest_price(STATION, 'B')  # newer, overwrites the pending slot
    sim.run_to_end()
    return sim


def test_superseded_price_a_is_never_dispatched():
    for seed in SEEDS:
        sim = _run_busy_then_superseded(seed)
        assert all(r.price != 'A' for r in sim.sends), seed
        assert all(price != 'A' for _, _, price in sim.deliveries), seed


def test_single_dispatch_after_busy_carries_newest_price_b():
    for seed in SEEDS:
        sim = _run_busy_then_superseded(seed)
        sends = [r for r in sim.sends if r.station == STATION]
        assert [r.price for r in sends] == ['X', 'B'], seed
        followups = sends[1:]
        assert len(followups) == 1 and followups[0].price == 'B', seed
        assert sim.send_counts()[STATION] == 2, seed
        assert all(r.acknowledged_at is not None for r in sends), seed
        assert sim.held_prices()[STATION] == 'B', seed
