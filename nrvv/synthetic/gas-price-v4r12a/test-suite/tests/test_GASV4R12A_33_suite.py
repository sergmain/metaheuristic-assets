import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)


def _new_sim(seed):
    sim = Simulation(seed, stations=('s1', 's2'), stop_tick=1, fault_window=(0, 0),
                     max_delay=2, loss=0.0)
    sim.source_schedule = {}
    sim.attach(lambda send: app.Server(send_update=send))
    return sim


def _delivered_prices(sim, station):
    return [r.price for r in sim.sends
            if r.station == station and not r.lost and r.delivered_tick is not None]


def test_each_station_gets_update_with_its_latest_desired_price():
    for seed in SEEDS:
        sim = _new_sim(seed)
        sim.server.accept_desired_price('s1', 0.90)
        sim.server.accept_desired_price('s1', 1.25)
        sim.server.accept_desired_price('s2', 2.10)
        sim.step()
        sim.run_until_idle(max_ticks=200)
        s1 = _delivered_prices(sim, 's1')
        assert 1.25 in s1, (seed, s1)
        assert 0.90 not in s1, (seed, s1)
        assert 2.10 in _delivered_prices(sim, 's2'), seed


def test_each_station_displays_its_own_latest_desired_price():
    for seed in SEEDS:
        sim = _new_sim(seed)
        sim.server.accept_desired_price('s1', 0.90)
        sim.server.accept_desired_price('s1', 1.25)
        sim.server.accept_desired_price('s2', 2.10)
        sim.step()
        sim.run_until_idle(max_ticks=200)
        assert sim.stations['s1'].displayed == 1.25, seed
        assert sim.stations['s2'].displayed == 2.10, seed


def test_latest_price_wins_when_accepted_after_an_earlier_publication():
    for seed in SEEDS:
        sim = _new_sim(seed)
        sim.server.accept_desired_price('s1', 0.90)
        sim.step()
        sim.server.accept_desired_price('s1', 1.25)
        sim.run_until_idle(max_ticks=200)
        assert sim.stations['s1'].displayed == 1.25, seed
