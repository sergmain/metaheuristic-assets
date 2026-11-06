import importlib

import app
from nrvv_env import Simulation

STATION = 'S1'
SEEDS = (1, 2, 3)
FOREVER = 10 ** 6


def _fresh_app(ports):
    importlib.reload(app)  # no state carried over between simulations
    app.connect(ports)
    return app


def _sim(seed, unreachable=()):
    sim = Simulation(seed, _fresh_app, station_ids=(STATION,), horizon=0, loss_rate=0.0)
    sim.stations[STATION].unreachable = list(unreachable)
    return sim


def _change(sim, at, price):
    sim._push(at, 'change', (STATION, price))


def _prices(sim):
    return [s.price for s in sim.sends if s.station_id == STATION]


def test_due_time_sends_desired_price_once_when_it_differs_and_nothing_in_flight():
    for seed in SEEDS:
        sim = _sim(seed)
        _change(sim, 1, 100)
        sim.advance_to(1 + 61)  # the price change, then a due time
        assert _prices(sim) == [100], seed
        sim.advance_to(200)
        assert _prices(sim) == [100], seed
        assert sim.applied_price(STATION) == 100, seed


def test_due_time_sends_nothing_when_desired_equals_held():
    for seed in SEEDS:
        sim = _sim(seed)
        _change(sim, 1, 100)
        sim.advance_to(120)
        assert sim.applied_price(STATION) == 100, seed  # held price is now 100
        assert _prices(sim) == [100], seed
        sim.advance_to(120 + 61)  # a due time with desired == held
        assert _prices(sim) == [100], seed


def test_due_time_sends_nothing_when_outstanding_send_carries_desired():
    for seed in SEEDS:
        sim = _sim(seed, unreachable=[(0, FOREVER)])  # never delivered, so it stays outstanding
        _change(sim, 1, 100)
        while not _prices(sim) and sim.now < 60:
            sim.step()
        assert _prices(sim) == [100], seed
        sim.step()  # a due time while the send is outstanding (abandonment is 30 s away)
        assert _prices(sim) == [100], seed


def test_price_change_sends_only_when_desired_differs_and_nothing_in_flight():
    for seed in SEEDS:
        # desired differs from held (none held) and nothing in flight
        sim = _sim(seed)
        _change(sim, 1, 100)
        sim.advance_to(2)
        assert _prices(sim) == [100], seed

        # desired equals held
        sim = _sim(seed)
        _change(sim, 1, 100)
        sim.advance_to(120)
        assert sim.applied_price(STATION) == 100, seed
        _change(sim, 121, 100)
        sim.advance_to(122)
        assert _prices(sim) == [100], seed

        # outstanding send carries desired
        sim = _sim(seed, unreachable=[(0, FOREVER)])
        _change(sim, 1, 100)
        _change(sim, 3, 100)
        sim.advance_to(4)
        assert _prices(sim) == [100], seed


def test_acknowledgement_sends_only_when_desired_differs_and_nothing_in_flight():
    for seed in SEEDS:
        # desired moves on while the only send is in flight; the acknowledgement then triggers one send
        sim = _sim(seed)
        _change(sim, 1, 100)
        _change(sim, 1, 120)
        sim.advance_to(120)
        assert _prices(sim) == [100, 120], seed

        # the outstanding send carries desired; its acknowledgement leaves nothing to send
        sim = _sim(seed)
        _change(sim, 1, 100)
        _change(sim, 1, 100)
        sim.advance_to(120)
        assert _prices(sim) == [100], seed


def test_abandonment_sends_only_when_desired_differs_and_nothing_in_flight():
    for seed in SEEDS:
        # the send is lost to an unreachable window; abandonment leaves desired != held with nothing in flight
        sim = _sim(seed, unreachable=[(0, 10)])
        _change(sim, 1, 100)
        sim.advance_to(120)
        assert _prices(sim) == [100, 100], seed
        sim.advance_to(200)
        assert _prices(sim) == [100, 100], seed

        # desired equals held when the outstanding send is abandoned
        sim = _sim(seed)
        _change(sim, 1, 100)
        sim.advance_to(120)
        assert sim.applied_price(STATION) == 100, seed
        sim.stations[STATION].unreachable = [(121, 131)]
        _change(sim, 121, 120)
        _change(sim, 122, 100)
        sim.advance_to(200)
        assert _prices(sim) == [100, 120], seed
