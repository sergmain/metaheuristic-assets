"""Suite for TMPGASDF1-27 / requirement TMPGASDF1-7.

Criterion: for a single station, once a first update is sent and before it is
acknowledged, triggers that would otherwise cause an update must not cause any
further send; when the acknowledgement is processed the outstanding slot is
cleared, knownDisplayed becomes exactly the price carried by the acknowledged
update, and the evaluation is re-run, so at most one unacknowledged update exists
per station at any moment and the next update is sent only after the predecessor
is acknowledged.

Everything is driven through ``nrvv_env`` only; ``app`` is observed through the
send-update port it is given, the acknowledgement path, and its read-only
``inspect``.
"""
import app
from nrvv_env import Simulation


# -- helpers -----------------------------------------------------------------

def _build(seed, **kw):
    """A connected service + simulation. No auto script unless asked."""
    sim = Simulation(seed=seed, **kw)
    server = app.Service(sim.send_update)
    sim.connect(server)
    return sim, server


def _field(view, *names):
    """Read a logical field from inspect()'s result tolerant to key spelling."""
    if isinstance(view, dict):
        for n in names:
            if n in view:
                return view[n]
    for n in names:
        if hasattr(view, n):
            return getattr(view, n)
    raise KeyError("none of %r present in %r" % (names, view))


def _known_displayed(server, station):
    return _field(server.inspect(station),
                  "known_displayed", "known-displayed", "knownDisplayed")


def _latest_desired(server, station):
    return _field(server.inspect(station),
                  "latest_desired", "latest-desired", "latestDesired")


def _outstanding(server, station):
    return _field(server.inspect(station),
                  "outstanding", "outstanding_price", "outstanding-price",
                  "outstanding_price_or_none", "outstanding-price-or-none")


def _deliver_pending(sim):
    """Deliver every currently-pending update (single-station callers only)."""
    while sim.pending_updates():
        sim.step()


def _deliver_head_ack(sim, station):
    """Deliver exactly the queued acknowledgements for one station."""
    while sim.stations[station].ack_queue:
        sim.step()


# -- tests -------------------------------------------------------------------

def test_no_further_send_while_update_outstanding():
    """More desired prices while an update is outstanding emit no new send."""
    sim, server = _build(seed=1, num_bursts=0)

    sim.inject_desired("S0", 5)          # first update -> one send
    assert len(sim.send_log) == 1
    first = sim.send_log[0]
    assert first.station == "S0" and first.price == 5

    # Conditions that would otherwise trigger an update arrive, un-acked.
    sim.inject_desired("S0", 9)
    sim.inject_desired("S0", 12)
    sim.inject_desired("S0", 9)

    # No further update is sent to the station.
    assert len(sim.send_log) == 1
    assert _outstanding(server, "S0") == 5


def test_ack_clears_slot_sets_known_and_resends_latest():
    """Acking the outstanding update clears the slot, records its price, re-sends."""
    sim, server = _build(seed=2, num_bursts=0)

    sim.inject_desired("S0", 5)
    sim.inject_desired("S0", 9)          # latest desired, but still one send
    assert len(sim.send_log) == 1

    _deliver_pending(sim)                # station now displays 5, ack queued
    assert sim.displayed("S0") == 5
    assert len(sim.send_log) == 1        # still nothing new while outstanding

    _deliver_head_ack(sim, "S0")         # service processes the acknowledgement

    # Slot cleared, re-evaluation ran and sent the successor for latest desired.
    assert len(sim.send_log) == 2
    second = sim.send_log[1]
    assert second.station == "S0" and second.price == 9
    # knownDisplayed is exactly the acked update's price, not the latest desired.
    assert _known_displayed(server, "S0") == 5
    assert _outstanding(server, "S0") == 9


def test_known_displayed_is_acked_price_not_latest_desired():
    """knownDisplayed after an ack equals the acked update's price alone."""
    sim, server = _build(seed=3, num_bursts=0)

    sim.inject_desired("S0", 7)
    # Pile up newer desired values before anything is delivered/acked.
    sim.inject_desired("S0", 11)
    sim.inject_desired("S0", 4)
    assert len(sim.send_log) == 1
    acked_price = sim.send_log[0].price   # == 7

    _deliver_pending(sim)
    _deliver_head_ack(sim, "S0")

    assert _known_displayed(server, "S0") == acked_price
    assert _known_displayed(server, "S0") != _latest_desired(server, "S0")


def test_successor_sent_only_after_predecessor_acked():
    """Each successive send happens only across an intervening acknowledgement."""
    sim, server = _build(seed=4, num_bursts=0)

    prices = [2, 8, 15, 3]
    for p in prices:
        sim.inject_desired("S0", p)
        # Only the very first injection may have produced a send so far; after
        # that the slot is occupied until we ack below.

    assert len(sim.send_log) == 1        # only one outstanding despite 4 inputs
    assert sim.send_log[0].price == prices[0]

    # Now acknowledge, step by step; exactly one new send should appear per ack,
    # and never more than one outstanding at a time.
    seen_prices = [sim.send_log[0].price]
    for _ in range(10):
        _deliver_pending(sim)
        before = len(sim.send_log)
        _deliver_head_ack(sim, "S0")
        after = len(sim.send_log)
        assert after - before <= 1       # at most the single successor
        if after > before:
            seen_prices.append(sim.send_log[-1].price)
        # outstanding count never exceeds one
        sent = sum(1 for r in sim.send_log if r.station == "S0")
        acked = sum(1 for r in sim.ack_log if r.station == "S0")
        assert 0 <= sent - acked <= 1
        if sim.is_quiescent():
            break

    # Converged to the final desired value, nothing outstanding.
    assert seen_prices[-1] == prices[-1]
    assert _outstanding(server, "S0") is None
    assert _known_displayed(server, "S0") == prices[-1]
    assert _latest_desired(server, "S0") == prices[-1]


def test_at_most_one_outstanding_per_station_throughout_run():
    """Across a seeded run no station ever has more than one update outstanding."""
    for seed in (1, 2, 3, 7, 42):
        sim, server = _build(seed=seed)
        steps = 0
        while True:
            ev = sim.step()
            steps += 1
            assert steps < 1000000
            for sid in sim.station_ids:
                sent = sum(1 for r in sim.send_log if r.station == sid)
                acked = sum(1 for r in sim.ack_log if r.station == sid)
                assert 0 <= sent - acked <= 1
            if ev is None:
                break


def test_update_ids_monotonic_per_station():
    """Per-station update identifiers are assigned strictly increasing."""
    for seed in (5, 11, 23):
        sim, _ = _build(seed=seed)
        sim.run()
        for sid in sim.station_ids:
            ids = [r.update_id for r in sim.send_log if r.station == sid]
            assert ids == sorted(ids)
            assert len(ids) == len(set(ids))


def test_converges_to_latest_desired_at_quiescence():
    """At quiescence each station's known/displayed equal its last desired price."""
    for seed in (1, 4, 9, 30):
        sim, server = _build(seed=seed)
        sim.run()
        assert sim.is_quiescent()

        last_desired = {}
        for rec in sim.input_log:
            last_desired[rec.station] = rec.price

        for sid, want in last_desired.items():
            assert _outstanding(server, sid) is None
            assert _known_displayed(server, sid) == want
            assert _latest_desired(server, sid) == want
            assert sim.displayed(sid) == want
