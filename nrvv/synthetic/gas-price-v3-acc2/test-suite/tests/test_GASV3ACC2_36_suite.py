"""Suite for TEST_CASE GASV3ACC2-36 / requirement GASV3ACC2-15.

An update counts as received only upon the station's acknowledgement. Only then
does the server advance the last-acknowledged mirror to the value of the single
outstanding update and clear the outstanding flag. Before the ACK arrives the
mirror and flag must stay put; a redundant ACK with nothing outstanding must not
advance the mirror again. Because ACKs return in send order and at most one
update per station is outstanding, each ACK is paired with exactly its update.

Everything is driven through the `nrvv_env` simulation: the test plays the
price-producing environment (submit-desired-price, GASV3ACC2-17) and the
ACK-delivering environment (acknowledgement-received, GASV3ACC2-18), observes
through get-station-state (GASV3ACC2-19), and lets the simulation's transport
carry each emitted update through deliver/ack. No other fake is introduced.
"""

import inspect

import app
import nrvv_env


# --------------------------------------------------------------------------
# Wiring + robust reading of the opaque get-station-state record.
# --------------------------------------------------------------------------

def _server_factory():
    """The CapWords server class of `app`, whose ctor takes the transmit port."""
    if hasattr(app, "Server"):
        return app.Server
    wanted = ("submit_desired_price", "acknowledgement_received",
              "get_station_state")
    for name in dir(app):
        obj = getattr(app, name)
        if inspect.isclass(obj) and name[:1].isupper():
            if all(hasattr(obj, m) for m in wanted):
                return obj
    raise AssertionError("no server class found in app")


def _connect(sim):
    """Build the server with its outbound port wired to the sim, then bind it."""
    return sim.connect(_server_factory())


def _as_mapping(state):
    """Best-effort view of the state record as an ordered name -> value map."""
    if isinstance(state, dict):
        return dict(state)
    asdict = getattr(state, "_asdict", None)
    if callable(asdict):
        try:
            return dict(asdict())
        except Exception:
            pass
    d = getattr(state, "__dict__", None)
    if d:
        return {k: v for k, v in d.items() if not k.startswith("_")}
    return None


def _is_number_or_none(v):
    return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool))


def _find_price(mapping, substrs):
    for k, v in mapping.items():
        if not _is_number_or_none(v):
            continue
        kl = str(k).lower()
        if any(s in kl for s in substrs):
            return v
    raise KeyError("no price field matching %r in %r" % (substrs, mapping))


def _find_flag(mapping):
    names = ("outstand", "pending", "inflight", "in_flight", "await",
             "unack", "dirty", "busy", "flag")
    for k, v in mapping.items():
        if any(s in str(k).lower() for s in names):
            return v
    for v in mapping.values():
        if isinstance(v, bool):
            return v
    raise KeyError("no outstanding-flag field in %r" % (mapping,))


def _desired(state):
    m = _as_mapping(state)
    if m is not None:
        return _find_price(m, ("desir", "target", "want", "goal", "latest"))
    return state[0]


def _acked(state):
    m = _as_mapping(state)
    if m is not None:
        return _find_price(m, ("acknowledg", "ack", "mirror", "confirm",
                               "settl"))
    return state[1]


def _flag(state):
    m = _as_mapping(state)
    if m is not None:
        return _find_flag(m)
    return state[2]


def _step(sim, kind):
    """Advance the transport by exactly one action and assert what it was."""
    action = sim.step()
    assert action is not None, "expected a %r action but nothing was available" % (kind,)
    assert action[0] == kind, "expected %r action, got %r" % (kind, action)
    return action


# --------------------------------------------------------------------------
# Tests.
# --------------------------------------------------------------------------

def test_ack_advances_mirror_to_outstanding_value_and_clears_flag():
    """Core GASV3ACC2-36 flow on a single station.

    Settle a prior value, open exactly one new outstanding update, confirm the
    mirror and flag are untouched before the ACK (both right after submit and
    after delivery), then confirm the ACK advances the mirror to the outstanding
    update's value and clears the flag.
    """
    sim = nrvv_env.Simulation([], seed=0)
    server = _connect(sim)
    s = "S0"
    prior, latest = 7, 19

    # Settle the prior value: emitted, delivered, acknowledged.
    server.submit_desired_price(s, prior)
    sim.run()
    assert sim.in_flight == []
    base = sim.get_station_state(s)
    assert _acked(base) == prior
    assert not _flag(base)

    # Exactly one new outstanding update; mirror still holds the prior value.
    server.submit_desired_price(s, latest)
    inflight = sim.in_flight
    assert len(inflight) == 1
    assert inflight[0].station == s and inflight[0].price == latest
    pre = sim.get_station_state(s)
    assert _desired(pre) == latest
    assert _acked(pre) == prior          # prior value, before any ACK
    assert _flag(pre)                    # outstanding flag set

    # Before the ACK arrives (update delivered to the station): unchanged.
    _step(sim, "deliver")
    assert sim.applied(s) == latest      # station adopted it...
    mid = sim.get_station_state(s)
    assert _acked(mid) == prior          # ...but the server mirror has not moved
    assert _flag(mid)

    # The station's acknowledgement arrives.
    _step(sim, "ack")
    post = sim.get_station_state(s)
    assert _acked(post) == latest        # advanced to the outstanding value
    assert not _flag(post)               # flag cleared
    assert sim.in_flight == []


def test_second_ack_without_outstanding_does_not_advance():
    """A redundant ACK, with no update outstanding, causes no further advance."""
    sim = nrvv_env.Simulation([], seed=0)
    server = _connect(sim)
    s = "S0"
    prior, latest = 11, 22

    server.submit_desired_price(s, prior)
    sim.run()
    server.submit_desired_price(s, latest)
    _step(sim, "deliver")
    _step(sim, "ack")
    settled = sim.get_station_state(s)
    assert _acked(settled) == latest
    assert not _flag(settled)
    assert sim.in_flight == []

    emissions_before = len(sim.sent)

    # A second acknowledgement for the same station, nothing outstanding.
    server.acknowledgement_received(s)

    after = sim.get_station_state(s)
    assert _acked(after) == latest       # no further advance
    assert _desired(after) == latest
    assert not _flag(after)
    assert len(sim.sent) == emissions_before   # and nothing re-emitted


def test_each_ack_paired_with_its_single_outstanding_update():
    """Across randomized transport orderings the mirror advances only on an ACK,
    and then to exactly the acknowledged update's value -- the in-order, one
    -outstanding-per-station pairing of GASV3ACC2-15.
    """
    names = ["S0", "S1", "S2"]
    for seed in (3, 29, 123, 777):
        sim = nrvv_env.Simulation.from_seed(
            seed, num_stations=3, num_events=30, station_names=names)
        _connect(sim)

        last_acked = {}
        seen = set()
        while True:
            action = sim.step()
            if action is None:
                break
            if action[0] == "submit":
                station = action[1]
            else:                       # deliver / ack carry the update
                station = action[1].station

            cur = _acked(sim.get_station_state(station))
            if action[0] == "ack":
                # Advanced to precisely the value of the outstanding update.
                assert cur == action[1].price
            elif station in seen:
                # submit and deliver never move the mirror.
                assert cur == last_acked[station]
            last_acked[station] = cur
            seen.add(station)

        # Quiescent: every station converged with its flag cleared.
        for station in names:
            final = sim.get_station_state(station)
            assert not _flag(final)
            assert _acked(final) == _desired(final)
