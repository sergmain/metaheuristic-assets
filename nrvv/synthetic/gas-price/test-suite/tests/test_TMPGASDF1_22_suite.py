"""Suite for TMPGASDF1-22 / requirement TMPGASDF1-5.

Criterion: when an earlier desired price for a station is set while an update
to that station is still unacknowledged, and one or more newer desired prices
are then set for that same station before the acknowledgement arrives, then upon
the acknowledgement the only value sent to that station is the most recent
desired price; no superseded intermediate desired price is ever transmitted.

Every test drives ``app`` exclusively through ``nrvv_env``. To make the scenario
deterministic we build the simulation with an EMPTY seeded script
(``num_bursts=0``) and drive it by hand: ``inject_desired`` issues a
set-desired-price call, and ``step`` executes the single scheduled transport
event that is available at each point (so the seeded scheduler's choice is
forced and the run is identical for every seed).
"""
import app
from nrvv_env import Simulation

SEEDS = (1, 7, 99)


def _make(seed):
    sim = Simulation(seed, num_bursts=0)
    server = app.Service(sim.send_update)
    sim.connect(server)
    return sim


def _sends_for(sim, station):
    return [r for r in sim.send_log if r.station == station]


def _deliveries_for(sim, station):
    return [r for r in sim.delivery_log if r.station == station]


def test_newer_price_set_after_delivery_before_ack_coalesces():
    """Deliver the first update, then supersede it twice before acknowledging.

    Only the first price and the most recent price are ever sent; the single
    intermediate price is never transmitted nor delivered.
    """
    S = "S0"
    first, intermediate, newest = 4, 11, 17
    for seed in SEEDS:
        sim = _make(seed)

        # Earliest desired price -> one update goes out (slot now outstanding).
        sim.inject_desired(S, first)
        assert [r.price for r in _sends_for(sim, S)] == [first]

        # Deliver that update to the station but do NOT acknowledge it yet.
        sim.step()
        assert sim.displayed(S) == first

        # Set newer desired prices while the update remains unacknowledged.
        sim.inject_desired(S, intermediate)
        sim.inject_desired(S, newest)
        # Nothing new may be sent while an update is outstanding.
        assert [r.price for r in _sends_for(sim, S)] == [first]

        # Acknowledgement arrives: the slot clears and the service re-evaluates.
        sim.step()

        # Upon acknowledgement exactly the most recent desired price is sent.
        assert [r.price for r in _sends_for(sim, S)] == [first, newest]

        # Drive to quiescence and check nothing superseded ever appeared.
        sim.run()
        assert intermediate not in [r.price for r in _sends_for(sim, S)]
        assert intermediate not in [r.price for r in _deliveries_for(sim, S)]
        assert [r.price for r in _sends_for(sim, S)] == [first, newest]
        assert sim.displayed(S) == newest
        assert sim.is_quiescent()


def test_newer_prices_set_before_delivery_coalesce():
    """Supersede the in-flight update before it is even delivered.

    The update is unacknowledged from the moment it is sent, so prices set before
    its delivery are still \"in flight\" supersessions and must be coalesced.
    """
    S = "S1"
    first, mid_a, mid_b, newest = 3, 8, 14, 19
    for seed in SEEDS:
        sim = _make(seed)

        sim.inject_desired(S, first)
        assert [r.price for r in _sends_for(sim, S)] == [first]

        # Newer desired prices arrive while the first update is still in flight
        # (sent, not yet delivered, not yet acknowledged).
        sim.inject_desired(S, mid_a)
        sim.inject_desired(S, mid_b)
        sim.inject_desired(S, newest)
        assert [r.price for r in _sends_for(sim, S)] == [first]

        # Deliver the first update, then acknowledge it.
        sim.step()  # deliver update
        sim.step()  # deliver acknowledgement -> re-evaluation sends newest

        assert [r.price for r in _sends_for(sim, S)] == [first, newest]

        sim.run()
        sent_prices = [r.price for r in _sends_for(sim, S)]
        for superseded in (mid_a, mid_b):
            assert superseded not in sent_prices
            assert superseded not in [r.price for r in _deliveries_for(sim, S)]
        assert sent_prices == [first, newest]
        assert sim.displayed(S) == newest
        assert sim.is_quiescent()


def test_many_intermediate_prices_all_coalesced_to_latest():
    """A long burst of supersessions collapses to a single send of the latest."""
    S = "S2"
    first = 2
    intermediates = [5, 6, 7, 9, 10, 12]
    newest = 15
    for seed in SEEDS:
        sim = _make(seed)

        sim.inject_desired(S, first)
        sim.step()  # deliver the first update
        assert sim.displayed(S) == first
        assert [r.price for r in _sends_for(sim, S)] == [first]

        # Many newer desired prices before the acknowledgement.
        for p in intermediates:
            sim.inject_desired(S, p)
        sim.inject_desired(S, newest)
        assert [r.price for r in _sends_for(sim, S)] == [first]

        sim.step()  # acknowledgement -> only the latest is sent
        assert [r.price for r in _sends_for(sim, S)] == [first, newest]

        sim.run()
        sent_prices = [r.price for r in _sends_for(sim, S)]
        delivered_prices = [r.price for r in _deliveries_for(sim, S)]
        for superseded in intermediates:
            assert superseded not in sent_prices
            assert superseded not in delivered_prices
        assert sent_prices == [first, newest]
        assert sim.displayed(S) == newest
        assert sim.is_quiescent()


def test_two_coalescing_cycles_in_a_row_each_sends_only_latest():
    """Repeated supersession cycles: each cycle emits only its latest value."""
    S = "S3"
    c1_first, c1_mid, c1_last = 4, 9, 13
    c2_mid, c2_last = 6, 18
    for seed in SEEDS:
        sim = _make(seed)

        # --- cycle 1 -------------------------------------------------------
        sim.inject_desired(S, c1_first)
        sim.step()  # deliver first update
        sim.inject_desired(S, c1_mid)
        sim.inject_desired(S, c1_last)
        assert [r.price for r in _sends_for(sim, S)] == [c1_first]
        sim.step()  # ack -> send c1_last only
        assert [r.price for r in _sends_for(sim, S)] == [c1_first, c1_last]

        # --- cycle 2 (a fresh update is now outstanding: c1_last) ----------
        sim.step()  # deliver the c1_last update
        assert sim.displayed(S) == c1_last
        sim.inject_desired(S, c2_mid)
        sim.inject_desired(S, c2_last)
        assert [r.price for r in _sends_for(sim, S)] == [c1_first, c1_last]
        sim.step()  # ack -> send c2_last only
        assert [r.price for r in _sends_for(sim, S)] == [c1_first, c1_last, c2_last]

        sim.run()
        sent_prices = [r.price for r in _sends_for(sim, S)]
        for superseded in (c1_mid, c2_mid):
            assert superseded not in sent_prices
            assert superseded not in [r.price for r in _deliveries_for(sim, S)]
        assert sent_prices == [c1_first, c1_last, c2_last]
        assert sim.displayed(S) == c2_last
        assert sim.is_quiescent()
