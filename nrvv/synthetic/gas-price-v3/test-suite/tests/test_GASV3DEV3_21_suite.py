"""Suite for TEST_CASE GASV3DEV3-21 (requirement GASV3DEV3-8).

Criterion: with a station's update already outstanding (in-flight), feed it a
sequence of two or more desired prices one after another before that outstanding
period ends and observe:
  * no output/transmission occurs for any of these arrivals;
  * the station's single 'pending' slot is created if absent and ends holding
    exactly the value of the LAST-arrived desired price;
  * every earlier arrived price has been overwritten/discarded, is retained
    nowhere, and is never sent.

The suite drives ``app`` only through ``nrvv_env`` and uses the explicit,
deterministic drivers (no clock, no threads); the station-bound channel is left
undelivered so every burst arrival lands during one single outstanding period.
"""

import numbers

import app
import nrvv_env


# --------------------------------------------------------------------------- #
# Wiring helpers
# --------------------------------------------------------------------------- #

def _make_server(sim):
    """Produce the server object to attach.

    Prefers an explicit server type/factory exported by ``app`` (injecting the
    outbound send-update port however it will accept it); otherwise the module
    ``app`` itself is the server (its snake_case functions are the operations
    and ``attach(..., wire_outbound=True)`` installs the ``send_update`` port).
    """
    for name in ("Server", "PriceServer", "Coalescer",
                 "create_server", "make_server", "new_server", "build_server"):
        factory = getattr(app, name, None)
        if callable(factory):
            attempts = [
                ((), {"send_update": sim.outbound}),
                ((), {"outbound": sim.outbound}),
                ((sim.outbound,), {}),
                ((), {}),
            ]
            for args, kwargs in attempts:
                try:
                    return factory(*args, **kwargs)
                except TypeError:
                    continue
    return app


def _build(script, seed=0):
    sim = nrvv_env.Simulation(seed=seed, script=script)
    server = _make_server(sim)
    sim.attach(server, wire_outbound=True, port_attr="send_update")
    return sim


# --------------------------------------------------------------------------- #
# Shape-agnostic inspection of inspect-station results
# --------------------------------------------------------------------------- #

def _collect_numbers(obj, acc=None, seen=None, depth=0):
    """Recursively gather every numeric (int/float, non-bool) value reachable
    inside ``obj``: dict values, sequence elements, namedtuple fields, and the
    attributes of plain objects (``__dict__`` / ``__slots__``).

    Prices are ints; this lets us assert which prices a station's reported
    displayed/outstanding/pending state does and does not retain, without
    depending on the exact return shape of ``inspect-station``.
    """
    if acc is None:
        acc = set()
    if seen is None:
        seen = set()
    if depth > 8 or obj is None:
        return acc
    if isinstance(obj, bool):
        return acc
    if isinstance(obj, numbers.Number):
        acc.add(obj)
        return acc
    if isinstance(obj, (str, bytes, bytearray)):
        return acc
    oid = id(obj)
    if oid in seen:
        return acc
    seen.add(oid)
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, acc, seen, depth + 1)
        return acc
    if isinstance(obj, (list, tuple, set, frozenset)):
        for v in obj:
            _collect_numbers(v, acc, seen, depth + 1)
        return acc
    d = getattr(obj, "__dict__", None)
    if isinstance(d, dict) and d:
        for v in d.values():
            _collect_numbers(v, acc, seen, depth + 1)
    slots = getattr(type(obj), "__slots__", None)
    if slots:
        if isinstance(slots, str):
            slots = [slots]
        for s in slots:
            try:
                _collect_numbers(getattr(obj, s), acc, seen, depth + 1)
            except AttributeError:
                continue
    return acc


def _prices_sent(sim):
    return [price for _station, price in sim.sent]


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

def test_burst_during_inflight_emits_no_additional_sends():
    """Across several price sets/seeds: once the first update is outstanding, a
    burst of further desired prices for that station transmits nothing more."""
    cases = [
        (0, "ST-A", [111, 222, 333, 444]),
        (1, "ST-B", [500, 650, 720]),
        (7, "ST-C", [900, 100, 321, 654, 213]),
    ]
    for seed, station, prices in cases:
        script = [(station, p) for p in prices]
        sim = _build(script, seed=seed)

        # First submission: nothing outstanding yet -> the server emits, so an
        # update becomes outstanding (in-flight, left undelivered).
        sim.fire_submission()
        assert sim.sent == [(station, prices[0])]

        # Every remaining price arrives during that single outstanding period.
        for _ in prices[1:]:
            sim.fire_submission()

        # No output/transmission for any of the coalesced arrivals.
        assert sim.sent == [(station, prices[0])]
        assert len(sim.delivered) == 0
        assert len(sim.acks) == 0


def test_only_last_price_survives_and_is_flushed_on_ack():
    """The sole surviving pending price is the last-arrived one: when the
    outstanding period ends (ack), exactly that value is sent, and no earlier
    coalesced price is ever transmitted."""
    station = "ST-flush"
    p0, p1, p2, p3 = 111, 222, 333, 444
    script = [(station, p0), (station, p1), (station, p2), (station, p3)]
    sim = _build(script, seed=0)

    sim.fire_submission()                     # p0 -> outstanding
    for _ in range(3):
        sim.fire_submission()                 # p1, p2, p3 coalesce
    assert sim.sent == [(station, p0)]

    # End the outstanding period: deliver the in-flight update, then its ack.
    inflight = sim.pending_updates()
    assert len(inflight) == 1
    sim.deliver(inflight[0].seq)
    sim.deliver_ack()

    # Acknowledging flushes the pending slot -> only the last price is emitted.
    assert sim.sent == [(station, p0), (station, p3)]

    # Drive the flushed update to completion; nothing further is emitted.
    inflight2 = sim.pending_updates()
    assert len(inflight2) == 1
    sim.deliver(inflight2[0].seq)
    sim.deliver_ack()
    assert sim.quiescent()

    sent_prices = _prices_sent(sim)
    assert sent_prices == [p0, p3]
    assert p1 not in sent_prices        # overwritten earlier value: never sent
    assert p2 not in sent_prices        # overwritten earlier value: never sent
    assert sim.displayed(station) == p3


def test_pending_slot_holds_only_most_recent_value():
    """While the update is outstanding, the station's reported state retains the
    last-arrived price and none of the earlier coalesced ones."""
    station = "ST-pending"
    p0, p1, p2, p3 = 111, 222, 333, 444
    script = [(station, p0), (station, p1), (station, p2), (station, p3)]
    sim = _build(script, seed=0)

    sim.fire_submission()                     # p0 -> outstanding
    for _ in range(3):
        sim.fire_submission()                 # p1, p2, p3 arrive in flight
    assert sim.sent == [(station, p0)]        # still nothing new transmitted

    nums = _collect_numbers(sim.inspect(station))
    assert p3 in nums                         # pending ends holding the last one
    assert p1 not in nums                     # discarded, retained nowhere
    assert p2 not in nums                     # discarded, retained nowhere


def test_each_arrival_overwrites_previous_pending_value():
    """The single pending slot is overwriting, not accumulating: after each new
    arrival only that value is retained and the previous pending value is gone.
    """
    station = "ST-overwrite"
    p0, p1, p2, p3 = 111, 222, 333, 444
    script = [(station, p0), (station, p1), (station, p2), (station, p3)]
    sim = _build(script, seed=0)

    sim.fire_submission()                     # p0 -> outstanding, no pending yet
    nums = _collect_numbers(sim.inspect(station))
    assert p1 not in nums and p2 not in nums and p3 not in nums

    sim.fire_submission()                     # pending := p1 (created)
    nums = _collect_numbers(sim.inspect(station))
    assert p1 in nums
    assert p2 not in nums and p3 not in nums

    sim.fire_submission()                     # pending := p2 (overwrite p1)
    nums = _collect_numbers(sim.inspect(station))
    assert p2 in nums
    assert p1 not in nums                     # earlier value discarded
    assert p3 not in nums

    sim.fire_submission()                     # pending := p3 (overwrite p2)
    nums = _collect_numbers(sim.inspect(station))
    assert p3 in nums
    assert p1 not in nums and p2 not in nums  # all earlier values discarded

    # Throughout the burst, nothing beyond the first update was transmitted.
    assert sim.sent == [(station, p0)]
