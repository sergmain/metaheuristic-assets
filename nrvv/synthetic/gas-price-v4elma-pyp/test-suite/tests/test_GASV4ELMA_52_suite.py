import app
from nrvv_env import Simulation

STATION = 'station-1'
FIRST_PRICE = 100  # "A"
NEWER_PRICE = 105  # "B"
SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)


def _server(dispatch):
    return app.Server(dispatch_update=dispatch)


def _replace_while_unreachable(seed):
    """Set A then B while STATION is unreachable, then let it become reachable again."""
    sim = Simulation(seed=seed, server_factory=_server, stations=1, stop_time=0.0, horizon=30.0)
    (t_down, _), (t_up, _) = sim.reach_schedule[STATION][:2]
    sim.run_until(t_down)
    assert sim.stations[STATION].reachable is False
    assert sim.app.set_desired_price(STATION, FIRST_PRICE) == 'Accepted'
    assert sim.app.set_desired_price(STATION, NEWER_PRICE) == 'Accepted'
    sim.run_until(t_up)
    sim.run()
    return sim


def test_superseded_price_never_reaches_station():
    for seed in SEEDS:
        sim = _replace_while_unreachable(seed)
        for r in sim.trace:
            if r.station == STATION and r.kind in ('dispatch', 'deliver', 'display', 'ack'):
                assert r.price != FIRST_PRICE, 'price A reached the station (seed %d)' % seed


def test_update_after_replacement_carries_only_newer_price():
    for seed in SEEDS:
        sim = _replace_while_unreachable(seed)
        sent = [r for r in sim.trace if r.kind == 'dispatch' and r.station == STATION]
        assert sent, 'no update sent after reconnect (seed %d)' % seed
        assert all(r.price == NEWER_PRICE for r in sent), 'non-B update (seed %d)' % seed
