"""Suite for TMPGASDF1-24 / requirement TMPGASDF1-4.

Pass condition: an update is transmitted to a station if and only if its price
differs from the station's currently (known) displayed price. Equal-valued
updates (no-ops) must not be sent.

Every test drives ``app`` only through ``nrvv_env``. The seeded price-source
script is disabled (``num_bursts=0``) so that each test fully controls which
desired prices are issued, via ``Simulation.inject_desired``; the observable
``send_log`` records exactly the updates the service transmits.
"""
import app
from nrvv_env import Simulation


def _make(seed):
    """Build a server wired to a fresh, script-free simulation."""
    sim = Simulation(seed, num_bursts=0)
    server = app.Service(sim.send_update)
    sim.connect(server)
    return sim, server


def _converge(sim, station, price):
    """Issue one desired price and settle everything in flight.

    Returns the number of send-update invocations observed during this call.
    """
    before = len(sim.send_log)
    sim.inject_desired(station, price)
    sim.run()
    return len(sim.send_log) - before


def test_equal_update_is_not_sent():
    # A station known to already display price p: re-issuing p must send nothing.
    for seed in (1, 7, 42, 1234):
        sim, _server = _make(seed)
        s = sim.station_ids[0]

        # Bring the station to a known, confirmed displayed price p.
        first_sends = _converge(sim, s, 11)
        assert first_sends == 1          # None -> 11 differs, so one update
        assert sim.displayed(s) == 11

        sends_before = len(sim.send_log)
        deliveries_before = len(sim.delivery_log)

        # Re-issue the identical price: this is a no-op update.
        extra = _converge(sim, s, 11)

        assert extra == 0                              # nothing transmitted
        assert len(sim.send_log) == sends_before       # send_log unchanged
        assert len(sim.delivery_log) == deliveries_before
        assert sim.displayed(s) == 11                  # still showing p


def test_differing_update_is_sent():
    # A station known to display p: issuing q != p must send exactly one update
    # carrying q, and the station must end up displaying q.
    for seed in (2, 9, 99, 5555):
        sim, _server = _make(seed)
        s = sim.station_ids[0]

        _converge(sim, s, 4)
        assert sim.displayed(s) == 4

        sends_before = len(sim.send_log)
        extra = _converge(sim, s, 17)

        assert extra == 1                              # exactly one update sent
        sent = sim.send_log[-1]
        assert sent.station == s
        assert sent.price == 17                        # it carries the new price
        assert len(sim.send_log) == sends_before + 1
        assert sim.displayed(s) == 17


def test_iff_transmission_matches_price_change():
    # Over a mixed sequence of desired prices (equal and differing), the number
    # of transmitted updates must equal the number of actual display changes:
    # an update is sent iff its price differs from the current displayed price.
    sequence = [5, 5, 8, 8, 8, 3, 5, 5, 5, 3, 3, 3, 12]
    for seed in (0, 3, 21, 777):
        sim, server = _make(seed)
        s = sim.station_ids[1]

        current = None
        expected_total = 0
        for p in sequence:
            sends = _converge(sim, s, p)
            if p != current:
                assert sends == 1          # change -> exactly one transmission
                current = p
                expected_total += 1
            else:
                assert sends == 0          # no change -> nothing transmitted
            # The simulated station always shows the last value it received.
            assert sim.displayed(s) == current

        assert len(sim.send_log) == expected_total


def test_other_stations_untouched_by_equal_updates():
    # Suppressing a no-op update for one station must not cause spurious sends to
    # any station; only genuine display changes ever appear on the send port.
    for seed in (13, 64, 2024):
        sim, _server = _make(seed)
        a, b = sim.station_ids[0], sim.station_ids[2]

        _converge(sim, a, 6)
        _converge(sim, b, 6)
        baseline = len(sim.send_log)

        # Re-issue identical prices to both: both are no-ops.
        assert _converge(sim, a, 6) == 0
        assert _converge(sim, b, 6) == 0
        assert len(sim.send_log) == baseline

        # Now change only a: exactly one new send, and it targets a with the new
        # price; b is never touched.
        assert _converge(sim, a, 7) == 1
        assert len(sim.send_log) == baseline + 1
        last = sim.send_log[-1]
        assert last.station == a and last.price == 7
        assert sim.displayed(a) == 7
        assert sim.displayed(b) == 6
