"""Suite for TMPGASDF1-23 / requirement TMPGASDF1-9.

Criterion: with an update already outstanding (unacknowledged) for a station,
setting the desired price twice before any acknowledgement must

  * transmit nothing while the update is outstanding,
  * retain only the single most recent desired value (overwrite, not queue),
  * and, upon acknowledgement of the outstanding update, transmit exactly one
    price equal to the second (most recent) value -- never the superseded first.

Every test drives ``app`` solely through ``nrvv_env``. We build the simulation
with ``num_bursts=0`` so the seeded price-source script never fires; all desired
prices are issued manually with ``inject_desired`` and the clock-free transport is
advanced with ``step`` -- with only one thing ever in flight, ``step`` selects the
single available action deterministically for any seed.
"""
import app
from nrvv_env import Simulation


def _wire(seed):
    """Build a quiet simulation (no seeded script) wired to a fresh server."""
    sim = Simulation(seed=seed, num_bursts=0)
    server = app.Service(sim.send_update)
    sim.connect(server)
    return sim, server


def _drain(sim):
    """Advance the transport to quiescence; deterministic because only one event
    is ever available at a time in these single-station scenarios."""
    sim.run()


def test_no_send_while_outstanding():
    # First desired price triggers the one outstanding update.
    sim, _ = _wire(seed=1234)
    sim.inject_desired("S0", 3)
    assert len(sim.send_log) == 1, "first desired price must emit one update"
    assert sim.send_log[0].price == 3

    # Two further desired prices arrive before any acknowledgement.
    sim.inject_desired("S0", 7)
    sim.inject_desired("S0", 14)

    # Nothing may be transmitted while the update is outstanding.
    assert len(sim.send_log) == 1
    assert [r.price for r in sim.send_log] == [3]


def test_ack_transmits_exactly_the_second_value():
    sim, _ = _wire(seed=20260101)
    sim.inject_desired("S0", 3)           # outstanding update (value 3)
    sim.inject_desired("S0", 7)           # superseded first desired value
    sim.inject_desired("S0", 14)          # most recent desired value

    sends_before_ack = len(sim.send_log)
    assert sends_before_ack == 1

    # Deliver the outstanding update to the station, then its acknowledgement.
    sim.step()                            # delivery of update (no send)
    assert len(sim.send_log) == sends_before_ack
    sim.step()                            # acknowledgement -> re-evaluate & send

    # Acknowledgement caused exactly one new transmission.
    assert len(sim.send_log) == sends_before_ack + 1
    assert sim.send_log[-1].station == "S0"
    assert sim.send_log[-1].price == 14   # the most recent value


def test_superseded_first_value_never_transmitted():
    sim, _ = _wire(seed=99)
    sim.inject_desired("S0", 3)           # outstanding
    sim.inject_desired("S0", 7)           # first (to be superseded) -> coalesced
    sim.inject_desired("S0", 14)          # second / most recent

    _drain(sim)

    prices = [r.price for r in sim.send_log if r.station == "S0"]
    # 7 was overwritten in place, never queued, so it is never sent.
    assert 7 not in prices
    # The only values ever transmitted are the initial outstanding one and the
    # most recent desired value -- in that order, each exactly once.
    assert prices == [3, 14]


def test_coalesce_many_supersessions_keeps_only_latest():
    # Several desired prices set in quick succession while outstanding: all but
    # the last are overwritten in place.
    sim, _ = _wire(seed=5)
    sim.inject_desired("S0", 3)                    # outstanding
    for p in (6, 9, 12, 17):                       # bursts of supersessions
        sim.inject_desired("S0", p)
    assert len(sim.send_log) == 1                  # still nothing new sent

    _drain(sim)

    prices = [r.price for r in sim.send_log if r.station == "S0"]
    # Only the initial outstanding value and the single latest desired value.
    assert prices == [3, 17]
    for superseded in (6, 9, 12):
        assert superseded not in prices


def test_convergence_after_coalescing():
    sim, _ = _wire(seed=424242)
    sim.inject_desired("S0", 3)
    sim.inject_desired("S0", 7)
    sim.inject_desired("S0", 14)

    _drain(sim)

    # The station ends up displaying exactly the most recent desired value, and
    # it was reached with exactly two transmissions (outstanding + coalesced
    # latest), never the superseded 7.
    assert sim.displayed("S0") == 14
    prices = [r.price for r in sim.send_log if r.station == "S0"]
    assert prices == [3, 14]
    assert sim.is_quiescent()


def test_only_second_value_delivered_and_acknowledged_as_latest():
    sim, _ = _wire(seed=7777)
    sim.inject_desired("S0", 3)
    sim.inject_desired("S0", 7)
    sim.inject_desired("S0", 14)

    _drain(sim)

    # Across the whole run the superseded value is never delivered to the
    # station nor acknowledged.
    assert 7 not in [r.price for r in sim.delivery_log if r.station == "S0"]
    assert 7 not in [r.price for r in sim.ack_log if r.station == "S0"]
    # The final delivered/acknowledged price for S0 is the most recent desired.
    s0_deliveries = [r.price for r in sim.delivery_log if r.station == "S0"]
    assert s0_deliveries[-1] == 14
