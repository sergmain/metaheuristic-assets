'''GASV4ACCJ-6: a late older price update must not leave a station on a stale price.

The scenario is driven through nrvv_env: the app module is the server, the
simulation delivers its sends with random delay and loss, and the price
changes are made at fixed simulated seconds. The newest price P2 is set one
second after the older price P1, so a P1 send can arrive after P2 has been
applied. Whatever the transport order, the station must end on P2.
'''

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app  # noqa: E402
from nrvv_env import Simulation  # noqa: E402

STATION = 'S1'


def _run_older_then_newer(seed, p1, p2, loss_rate=0.1):
    # horizon=0 means the environment schedules no price changes of its own,
    # so the only desired-price changes are the two made below.
    sim = Simulation(seed, app, station_ids=(STATION,), horizon=0, loss_rate=loss_rate)
    sim.advance_to(0)
    app.set_desired_price(STATION, p1)  # older price P1 (earlier)
    sim.advance_to(1)
    app.set_desired_price(STATION, p2)  # newer price P2
    sim.run_until_idle()
    return sim


def _assert_station_on_newest(sim, p1, p2):
    deliveries = sim.stations[STATION].deliveries
    assert any(d.price == p2 for d in deliveries), 'newest price P2 was never delivered to the station'
    applied = sim.applied_price(STATION)
    assert applied != p1, 'station is left applying the older price P1 after out-of-order delivery'
    assert applied == p2, 'station applies %r, expected newest price %r' % (applied, p2)


def test_late_older_price_does_not_leave_station_on_stale_price():
    for seed in range(40):
        sim = _run_older_then_newer(seed, p1=90, p2=110)
        _assert_station_on_newest(sim, p1=90, p2=110)


def test_station_applies_newest_price_without_loss():
    for seed in range(20):
        sim = _run_older_then_newer(seed, p1=60, p2=140, loss_rate=0.0)
        _assert_station_on_newest(sim, p1=60, p2=140)


def test_station_applies_newest_price_under_heavy_loss():
    for seed in range(20):
        sim = _run_older_then_newer(seed, p1=130, p2=70, loss_rate=0.4)
        _assert_station_on_newest(sim, p1=130, p2=70)


def test_newest_price_holds_for_boundary_price_pairs():
    pairs = [(50, 51), (99, 100), (149, 50), (50, 150)]
    for p1, p2 in pairs:
        for seed in range(10):
            sim = _run_older_then_newer(seed, p1=p1, p2=p2)
            _assert_station_on_newest(sim, p1=p1, p2=p2)
