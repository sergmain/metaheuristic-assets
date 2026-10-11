"""Verifies GASV4ACCJ-7: do not resend a price the station already holds or is receiving."""

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5, 6, 7, 8, 9)
PRICE = 150
OTHER_PRICE = 120
STATIONS = ("S1", "S2", "S3")


def _new_run(seed):
    sim = Simulation(seed, changes=0, drop_probability=0.0)
    sim.connect(app)
    return sim


def _reachable_at(sim, station, start):
    when = start
    for begin, end in sim.unreachable_intervals(station):
        if begin <= when < end:
            when = end
    return when


def _go_to(sim, station, start):
    when = _reachable_at(sim, station, start)
    sim.request_wake_up(when)
    sim.run_until(when)
    return when


def _sends_to(sim, station):
    return [record for record in sim.sends() if record.station == station]


def test_acknowledged_price_is_not_resent():
    for seed in SEEDS:
        station = STATIONS[seed % len(STATIONS)]
        sim = _new_run(seed)
        _go_to(sim, station, 0.0)
        app.set_desired_price(station, PRICE)
        sim.run_until_quiet()
        sent = [(r.price, r.state) for r in _sends_to(sim, station)]
        assert sent == [(PRICE, "acked")], f"seed {seed}: precondition not met"

        _go_to(sim, station, sim.now + 30.0)
        before = len(sim.sends())
        app.set_desired_price(station, PRICE)
        sim.run_until(sim.now + 300.0)
        assert len(sim.sends()) == before, f"seed {seed}: acknowledged price was resent"


def test_price_already_in_flight_is_not_resent():
    for seed in SEEDS:
        station = STATIONS[seed % len(STATIONS)]
        sim = _new_run(seed)
        now = _go_to(sim, station, 0.0)
        app.set_desired_price(station, PRICE)
        sim.run_until(now)
        pending = [(r.price, r.state) for r in _sends_to(sim, station)]
        assert pending == [(PRICE, "in_transit")], f"seed {seed}: precondition not met"

        before = len(sim.sends())
        app.set_desired_price(station, PRICE)
        sim.run_until(now)
        assert len(sim.sends()) == before, f"seed {seed}: duplicate sent while in flight"
        sim.run_until_quiet()
        sim.run_until(sim.now + 300.0)
        assert len(sim.sends()) == before, f"seed {seed}: price resent after acknowledgement"


def test_price_not_held_or_pending_is_sent():
    for mode in ("fresh", "acked_other", "pending_other"):
        for seed in SEEDS:
            station = STATIONS[seed % len(STATIONS)]
            sim = _new_run(seed)
            now = _go_to(sim, station, 0.0)
            if mode == "acked_other":
                app.set_desired_price(station, OTHER_PRICE)
                sim.run_until_quiet()
            elif mode == "pending_other":
                app.set_desired_price(station, OTHER_PRICE)
                sim.run_until(now)
            before = len(sim.sends())
            app.set_desired_price(station, PRICE)
            sim.run_until_quiet()
            new = sim.sends()[before:]
            assert any(r.station == station and r.price == PRICE for r in new), f"{mode} seed {seed}: price not sent"
