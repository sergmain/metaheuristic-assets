"""Tests for TMPGASDF1-21 / TMPGASDF1-1.

Criterion: when a station's latest desired price is not known to already be
displayed by that station, the service produces a price update directed to that
station carrying that latest desired price; conversely, when that latest desired
price is known to already be displayed, the service produces no such update.

Everything is driven through ``app`` via the ``nrvv_env`` simulation only.
"""
import app
from nrvv_env import Simulation


def _sends_for(sim, station):
    return [r for r in sim.send_log if r.station == station]


def test_sends_update_for_fresh_station_not_known_displayed():
    # A station that has never displayed anything: its latest desired price is
    # trivially not known to be displayed, so an update must be produced for it.
    sim = Simulation(seed=1, num_bursts=0)
    server = app.Service(sim.send_update)
    sim.connect(server)

    sim.inject_desired("S0", 7)

    sends = _sends_for(sim, "S0")
    assert len(sends) >= 1, "expected a price update directed to S0"
    assert sends[-1].price == 7


def test_update_carries_the_latest_desired_price():
    # The produced update must carry exactly the station's latest desired price,
    # and must be directed to that station and no other.
    sim = Simulation(seed=2, num_bursts=0)
    server = app.Service(sim.send_update)
    sim.connect(server)

    sim.inject_desired("S3", 13)

    assert all(r.station == "S3" for r in sim.send_log)
    s3 = _sends_for(sim, "S3")
    assert len(s3) == 1
    assert s3[0].price == 13


def test_no_update_when_latest_desired_already_displayed():
    # Drive one price to full convergence (sent, delivered, acknowledged) so the
    # service knows the station now displays it, then set the same price again:
    # no further update may be produced for that station.
    sim = Simulation(seed=3, num_bursts=0)
    server = app.Service(sim.send_update)
    sim.connect(server)

    sim.inject_desired("S1", 5)
    sim.run()
    assert sim.displayed("S1") == 5

    before = _sends_for(sim, "S1")
    sim.inject_desired("S1", 5)  # equals what is known to be displayed
    after = _sends_for(sim, "S1")

    assert after == before, "no update must be produced when already displayed"


def test_sends_again_when_desired_changes_after_convergence():
    # After convergence at one price, a different desired price is again not known
    # to be displayed, so a fresh update carrying the new price must be produced.
    sim = Simulation(seed=4, num_bursts=0)
    server = app.Service(sim.send_update)
    sim.connect(server)

    sim.inject_desired("S2", 4)
    sim.run()
    assert sim.displayed("S2") == 4

    before = _sends_for(sim, "S2")
    sim.inject_desired("S2", 9)
    after = _sends_for(sim, "S2")

    assert len(after) == len(before) + 1
    assert after[-1].price == 9


def test_repeating_the_same_desired_price_produces_no_duplicate():
    # Setting the identical price twice while it is still being established, then
    # letting it converge, and finally setting it once more (now known displayed):
    # the final repeat must produce no update.
    sim = Simulation(seed=5, num_bursts=0)
    server = app.Service(sim.send_update)
    sim.connect(server)

    sim.inject_desired("S0", 11)
    sim.run()
    assert sim.displayed("S0") == 11

    before = _sends_for(sim, "S0")
    sim.inject_desired("S0", 11)
    sim.run()
    after = _sends_for(sim, "S0")

    assert after == before
    assert sim.displayed("S0") == 11


def test_converges_to_latest_desired_under_seeded_script():
    # End-to-end: across seeded scripts (including coalescing bursts), every
    # station that received a desired price ends up displaying its latest desired
    # price -- i.e. updates carrying the latest desired price were produced and
    # delivered -- and the run reaches quiescence.
    for seed in (10, 21, 37, 44):
        sim = Simulation(seed=seed)
        server = app.Service(sim.send_update)
        sim.connect(server)

        sim.run()
        assert sim.is_quiescent()

        latest = {}
        for rec in sim.input_log:
            latest[rec.station] = rec.price
        for station, price in latest.items():
            assert sim.displayed(station) == price, (
                "station %s should display its latest desired price" % station)
