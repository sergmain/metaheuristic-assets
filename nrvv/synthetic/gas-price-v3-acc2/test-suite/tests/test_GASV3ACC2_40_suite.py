"""Suite for TEST_CASE GASV3ACC2-40 (requirement GASV3ACC2-7).

Coalesce prices superseded while a send is outstanding: when several new desired
prices for a station arise before the service next sends an update to that
station, the service shall send only the most recent of those prices and shall
not separately send the superseded intermediate prices.

Every test drives `app` only through `nrvv_env`. The scenario needs a precise
interleaving (several submits must land while one update is still outstanding,
i.e. before the next send occurs), so instead of the RNG-driven ``step()`` the
tests perform the simulation's atomic environment actions in a fixed order via
``Simulation._perform`` -- the very mechanism ``step()`` itself uses to call the
server's inbound operations. No clock, no threads, no extra fakes; the runs are
fully deterministic by construction.
"""

import nrvv_env

import app


# --- deterministic environment-action helpers (all go through nrvv_env) -------

def _submit(sim, station, price):
    """Fire a producer event: the environment calls submit-desired-price."""
    sim._perform(("submit", station, price))


def _deliver(sim, station):
    """Deliver the station's outstanding (still-EMITTED) update."""
    for u in sim.in_flight:
        if u.station == station and u.state == nrvv_env.Update.EMITTED:
            sim._perform(("deliver", u))
            return u
    raise AssertionError("no deliverable update outstanding for %r" % (station,))


def _ack(sim, station):
    """Acknowledge the station's delivered-but-unacked update (clears it)."""
    for u in sim.in_flight:
        if u.station == station and u.state == nrvv_env.Update.DELIVERED:
            sim._perform(("ack", u))
            return u
    raise AssertionError("no acknowledgeable update outstanding for %r" % (station,))


def _prices_sent_to(sim, station):
    return [p for (s, p) in sim.sent if s == station]


# --- tests --------------------------------------------------------------------

def test_next_send_carries_only_the_final_superseded_price():
    """Earlier value, then later values ending in a final latest value, all
    arriving while a send is outstanding: the next send is exactly the latest."""
    sim = nrvv_env.Simulation([("S", 10), ("S", 20), ("S", 30)])
    sim.connect(app.Server)

    # First desired price on a fresh, idle, diverged station -> one send emitted.
    _submit(sim, "S", 10)
    assert sim.sent == [("S", 10)]

    # That update is now outstanding. Supply successive new desired prices
    # (20 then the final 30) before the next send to S occurs.
    _submit(sim, "S", 20)
    _submit(sim, "S", 30)
    # No new send is produced while the earlier send is still outstanding.
    assert sim.sent == [("S", 10)]

    # Resolve the outstanding update; the acknowledgement makes S idle and
    # triggers the next send.
    before = list(sim.sent)
    _deliver(sim, "S")
    _ack(sim, "S")
    new_sends = sim.sent[len(before):]

    # Exactly one price is sent as the next send, and it is the most recent one.
    assert new_sends == [("S", 30)]
    # The superseded intermediate price 20 is never sent as a separate update.
    assert 20 not in _prices_sent_to(sim, "S")
    assert _prices_sent_to(sim, "S") == [10, 30]


def test_many_intermediate_prices_collapse_to_single_latest_send():
    prices = [5, 15, 25, 35, 45]
    sim = nrvv_env.Simulation([("S", p) for p in prices])
    sim.connect(app.Server)

    _submit(sim, "S", prices[0])            # fresh station -> emits 5
    for p in prices[1:]:                    # 15, 25, 35, 45 all supersede
        _submit(sim, "S", p)
    assert sim.sent == [("S", 5)]           # coalesced while outstanding

    before = list(sim.sent)
    _deliver(sim, "S")
    _ack(sim, "S")
    assert sim.sent[len(before):] == [("S", 45)]   # exactly one, the latest

    # None of the superseded intermediates were sent as separate updates.
    for inter in (15, 25, 35):
        assert inter not in _prices_sent_to(sim, "S")
    assert _prices_sent_to(sim, "S") == [5, 45]


def test_coalescing_holds_until_ack_even_after_delivery():
    """Delivered-but-unacked is still outstanding: prices arriving then are
    coalesced, and the next send (triggered by the ack) carries only the last."""
    sim = nrvv_env.Simulation([("S", 100), ("S", 200), ("S", 300)])
    sim.connect(app.Server)

    _submit(sim, "S", 100)                  # emits 100
    assert sim.sent == [("S", 100)]
    _deliver(sim, "S")                      # delivered, but NOT yet acknowledged

    _submit(sim, "S", 200)                  # supersede while still outstanding
    _submit(sim, "S", 300)
    assert sim.sent == [("S", 100)]         # no separate sends for 200/300

    _ack(sim, "S")                          # clears outstanding -> next send
    assert sim.sent == [("S", 100), ("S", 300)]
    assert 200 not in _prices_sent_to(sim, "S")


def test_coalescing_is_independent_per_station():
    events = [("A", 1), ("B", 1), ("A", 2), ("A", 3), ("B", 2), ("B", 3)]
    sim = nrvv_env.Simulation(events)
    sim.connect(app.Server)

    _submit(sim, "A", 1)                    # fresh A -> emits A/1
    _submit(sim, "B", 1)                    # fresh B -> emits B/1
    assert sim.sent == [("A", 1), ("B", 1)]

    # Supersede each station's price while its own send is outstanding.
    _submit(sim, "A", 2)
    _submit(sim, "A", 3)
    _submit(sim, "B", 2)
    _submit(sim, "B", 3)
    assert sim.sent == [("A", 1), ("B", 1)]   # nothing new while outstanding

    _deliver(sim, "A")
    _ack(sim, "A")                          # A idle -> next send A/3
    _deliver(sim, "B")
    _ack(sim, "B")                          # B idle -> next send B/3

    assert sim.sent == [("A", 1), ("B", 1), ("A", 3), ("B", 3)]
    assert _prices_sent_to(sim, "A") == [1, 3]
    assert _prices_sent_to(sim, "B") == [1, 3]
    assert 2 not in _prices_sent_to(sim, "A")
    assert 2 not in _prices_sent_to(sim, "B")


def test_coalesced_run_converges_and_station_never_sees_intermediates():
    prices = [7, 17, 27, 37]
    sim = nrvv_env.Simulation([("S", p) for p in prices])
    sim.connect(app.Server)

    _submit(sim, "S", prices[0])            # emits 7
    for p in prices[1:]:                    # 17, 27, 37 supersede
        _submit(sim, "S", p)
    assert sim.sent == [("S", 7)]

    _deliver(sim, "S")
    _ack(sim, "S")                          # next send carries the latest, 37
    assert sim.sent == [("S", 7), ("S", 37)]

    _deliver(sim, "S")
    _ack(sim, "S")                          # converged: desired == acked, no more sends
    assert sim.sent == [("S", 7), ("S", 37)]

    # The station physically received only the two non-superseded updates;
    # the superseded intermediates were never transmitted nor delivered.
    assert sim.delivered == [("S", 7), ("S", 37)]
    assert sim.station("S").received_count == 2
    for inter in (17, 27):
        assert inter not in _prices_sent_to(sim, "S")
