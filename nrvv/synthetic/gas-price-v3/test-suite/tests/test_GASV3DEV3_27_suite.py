"""Suite for GASV3DEV3-27: convergence on acknowledgement.

On learning a station's acknowledgement the server must, in order:
  1. set the station's displayed value to its recorded sentPrice,
  2. clear outstanding?,
  3. clear sentPrice,
and then act on the pending slot:
  * empty            -> dispatch nothing, no further state change;
  * equals displayed -> clear pending, dispatch nothing (R5);
  * otherwise        -> dispatch exactly one update carrying the pending
                        value, move that value into sentPrice, set
                        outstanding?, clear pending.

Every test drives ``app`` only through ``nrvv_env`` and is deterministic
(fixed seeds, explicit drivers, no clock/threads).
"""

import collections

import app
import nrvv_env


# --------------------------------------------------------------------------
# Wiring: build a Simulation attached to the app-under-test.  The server is
# whatever ``app`` exposes -- either a ``Server`` class or the module itself --
# and the outbound send-update port is wired to the simulation so every
# emission is observed.
# --------------------------------------------------------------------------

def _make_server(sim):
    server_cls = getattr(app, "Server", None)
    if server_cls is not None:
        for args, kwargs in (((sim.outbound,), {}),
                             ((), {"send_update": sim.outbound}),
                             ((), {"outbound": sim.outbound}),
                             ((), {"send": sim.outbound})):
            try:
                return server_cls(*args, **kwargs), True
            except TypeError:
                continue
        try:
            return server_cls(), False
        except TypeError:
            pass
    return app, False


def _make_sim(seed=0, script=None):
    sim = nrvv_env.Simulation(seed=seed, script=script)
    server, wired = _make_server(sim)
    sim.attach(server)
    if not wired and getattr(server, "send_update", None) is not sim.outbound:
        setattr(server, "send_update", sim.outbound)
    return sim


# --------------------------------------------------------------------------
# Tolerant reader for the inspect-station query.  The Interface says the query
# returns the displayed value (or 'unknown'), whether an update is outstanding
# and its sent price, and the pending price (or 'none').  We normalise the
# common Python shapes (dict, namedtuple, attribute object, plain tuple) to a
# single State so the assertions describe the *state*, not the encoding.
# --------------------------------------------------------------------------

_MISSING = object()

_DISPLAYED_KEYS = ("displayed", "display", "displayed_value", "displayed_price",
                   "known", "value", "shown", "price")
_OUTSTANDING_KEYS = ("outstanding", "outstanding?", "is_outstanding",
                     "has_outstanding", "outstanding_flag")
_SENT_KEYS = ("sent_price", "sentPrice", "sent", "sent_value",
              "outstanding_price")
_PENDING_KEYS = ("pending", "pending_price", "pending_value")

State = collections.namedtuple("State", "displayed outstanding sent_price pending")


def _from_keys(mapping, keys):
    for k in keys:
        if k in mapping:
            return mapping[k]
    return _MISSING


def _from_attrs(obj, keys):
    for k in keys:
        if k.isidentifier() and hasattr(obj, k):
            return getattr(obj, k)
    return _MISSING


def _normalize_price(v):
    if v is _MISSING or v is None:
        return None
    if isinstance(v, str) and v.strip().lower() in ("unknown", "none", ""):
        return None
    return v


def read_state(raw):
    mapping = {}
    if isinstance(raw, dict):
        mapping = dict(raw)
    elif hasattr(raw, "_asdict"):
        try:
            mapping = dict(raw._asdict())
        except Exception:
            mapping = {}
    elif isinstance(raw, (tuple, list)):
        if len(raw) >= 4:
            mapping = {"displayed": raw[0], "outstanding": raw[1],
                       "sent_price": raw[2], "pending": raw[3]}
        elif len(raw) == 3:
            mapping = {"displayed": raw[0], "sent_price": raw[1],
                       "pending": raw[2]}
        elif len(raw) == 2:
            mapping = {"displayed": raw[0], "pending": raw[1]}

    def pick(keys):
        v = _from_keys(mapping, keys)
        if v is _MISSING:
            v = _from_attrs(raw, keys)
        return v

    displayed = _normalize_price(pick(_DISPLAYED_KEYS))
    sent_price = _normalize_price(pick(_SENT_KEYS))
    pending = _normalize_price(pick(_PENDING_KEYS))

    raw_out = pick(_OUTSTANDING_KEYS)
    if raw_out is _MISSING:
        outstanding = sent_price is not None
    elif isinstance(raw_out, str):
        outstanding = raw_out.strip().lower() in ("true", "yes",
                                                  "outstanding", "1")
    else:
        outstanding = bool(raw_out)

    return State(displayed, outstanding, sent_price, pending)


# --------------------------------------------------------------------------
# Branch 1: pending is empty -> confirm display, send nothing, idle.
# --------------------------------------------------------------------------

def test_ack_with_empty_pending_confirms_display_and_sends_nothing():
    st = "a-empty"
    sim = _make_sim(seed=0, script=[(st, 100)])

    sim.fire_submission()                      # idle station -> emit 100
    assert sim.sent == [(st, 100)]
    updates = sim.pending_updates()
    assert len(updates) == 1

    sim.deliver(updates[0].seq)                # station shows 100, ack queued
    assert sim.pending_acks()
    sim.deliver_ack()                          # the acknowledgement is learned

    # Pending was empty: no update dispatched, no further state change.
    assert sim.sent == [(st, 100)]
    assert sim.displayed(st) == 100

    state = read_state(sim.inspect(st))
    assert state.displayed == 100              # displayed set to sentPrice
    assert state.outstanding is False          # outstanding? cleared
    assert state.sent_price is None            # sentPrice cleared
    assert state.pending is None               # still empty


# --------------------------------------------------------------------------
# Branch 2: pending equals the now-displayed value -> suppress (R5).
# Two coalesced submissions (200 then 100) leave pending holding 100, which
# equals the value that becomes displayed on ack.
# --------------------------------------------------------------------------

def test_ack_with_pending_equal_to_display_is_suppressed():
    st = "b-equal"
    sim = _make_sim(seed=0, script=[(st, 100), (st, 200), (st, 100)])

    sim.fire_submission()                      # emit 100 (sentPrice = 100)
    sim.fire_submission()                      # outstanding -> pending 200
    sim.fire_submission()                      # outstanding -> pending 100
    assert sim.sent == [(st, 100)]             # only the first was sent
    updates = sim.pending_updates()
    assert len(updates) == 1

    sim.deliver(updates[0].seq)
    sim.deliver_ack()

    # Pending (100) equals displayed (100): pending cleared, nothing sent.
    assert sim.sent == [(st, 100)]
    assert sim.displayed(st) == 100

    state = read_state(sim.inspect(st))
    assert state.displayed == 100
    assert state.outstanding is False
    assert state.sent_price is None
    assert state.pending is None


# --------------------------------------------------------------------------
# Branch 3: pending differs -> flush exactly one update, re-arm outstanding.
# --------------------------------------------------------------------------

def test_ack_with_differing_pending_flushes_single_update():
    st = "c-diff"
    sim = _make_sim(seed=0, script=[(st, 100), (st, 200)])

    sim.fire_submission()                      # emit 100 (sentPrice = 100)
    sim.fire_submission()                      # outstanding -> pending 200
    assert sim.sent == [(st, 100)]
    updates = sim.pending_updates()
    assert len(updates) == 1

    sim.deliver(updates[0].seq)
    sim.deliver_ack()

    # Pending (200) differs from displayed (100): exactly one update flushed.
    assert sim.sent == [(st, 100), (st, 200)]
    # The station still shows the just-acked 100 (the flush is not yet delivered).
    assert sim.displayed(st) == 100

    state = read_state(sim.inspect(st))
    assert state.displayed == 100              # advanced to old sentPrice
    assert state.outstanding is True           # the flushed update is outstanding
    assert state.sent_price == 200             # pending value moved to sentPrice
    assert state.pending is None               # pending slot cleared


# --------------------------------------------------------------------------
# Aggregate: repeatedly exercising the three ack branches under reordered
# delivery converges each station's displayed value to its latest desired
# price, with nothing outstanding or pending.
# --------------------------------------------------------------------------

def test_repeated_ack_branches_converge_to_latest_desired():
    for seed in (0, 1, 2, 3, 7):
        stations = ["k%d-A" % seed, "k%d-B" % seed, "k%d-C" % seed]
        script = nrvv_env.random_script(seed, stations, 24)
        sim = _make_sim(seed=seed, script=script)

        sim.run()                              # drive to quiescence

        last = {}
        for station, price in script:
            last[station] = price

        for station, desired in last.items():
            state = read_state(sim.inspect(station))
            assert state.displayed == desired, (seed, station, state)
            assert state.outstanding is False, (seed, station, state)
            assert state.sent_price is None, (seed, station, state)
            assert state.pending is None, (seed, station, state)
            assert sim.displayed(station) == desired, (seed, station)
