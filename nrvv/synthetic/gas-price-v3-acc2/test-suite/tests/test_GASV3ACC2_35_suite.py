"""Tests for GASV3ACC2-35: all reconciliation state held server-side.

The criterion: after a desired price is set, the server holds, per station
alone, three values -- the latest desired price, a mirror of the price most
recently acknowledged by that station, and an outstanding flag. The station
keeps no version and performs no comparison. When desired diverges from the
mirror the server marks an update outstanding and sends it; on acknowledgement
the mirror advances to the acknowledged value. The station never rejects an
update and no send decision depends on station-held state.

Every test drives `app` only through `nrvv_env`.
"""

import app
import nrvv_env


# ---------------------------------------------------------------------------
# Accessing the server's observation surface (GASV3ACC2-19).
#
# get_station_state returns "{ latest desired price, last acknowledged price
# value, outstanding flag }". The exact container shape is not pinned down by
# the interface, so normalise whatever it returns to the ordered triple
# (desired, acknowledged, outstanding).
# ---------------------------------------------------------------------------

def _pick(remaining, needles):
    for k in list(remaining):
        lk = str(k).lower()
        for n in needles:
            if n in lk:
                remaining.remove(k)
                return k
    return None


def _mapping_triple(d):
    remaining = list(d.keys())
    out_k = _pick(remaining, ["outstand", "pending", "dirty", "inflight",
                              "in_flight", "await", "sending", "unacked",
                              "unack", "flag"])
    ack_k = _pick(remaining, ["acknowledg", "ack", "mirror", "confirm",
                              "applied", "last"])
    des_k = _pick(remaining, ["desire", "target", "wanted", "want", "goal",
                              "latest"])
    if out_k is not None and ack_k is not None and des_k is not None:
        return d[des_k], d[ack_k], d[out_k]
    vals = list(d.values())
    assert len(vals) == 3, (
        "get_station_state must expose exactly three values "
        "(desired, acknowledged, outstanding); got %r" % (list(d.keys()),)
    )
    return vals[0], vals[1], vals[2]


def _triple(state):
    if hasattr(state, "_asdict"):
        return _mapping_triple(dict(state._asdict()))
    if isinstance(state, dict):
        return _mapping_triple(state)
    if isinstance(state, (tuple, list)):
        assert len(state) == 3
        return state[0], state[1], state[2]
    d = {}
    for name in dir(state):
        if name.startswith("_"):
            continue
        try:
            v = getattr(state, name)
        except Exception:
            continue
        if callable(v):
            continue
        d[name] = v
    return _mapping_triple(d)


def _desired(state):
    return _triple(state)[0]


def _acknowledged(state):
    return _triple(state)[1]


def _outstanding(state):
    return bool(_triple(state)[2])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_state_holds_three_values_after_a_desired_price_is_set():
    sim = nrvv_env.Simulation([])
    server = sim.connect(app.Server)

    server.submit_desired_price("A", 42)

    desired, acknowledged, outstanding = _triple(server.get_station_state("A"))
    # The latest desired price is recorded.
    assert desired == 42
    # Nothing has been acknowledged yet, so the mirror is not that price.
    assert acknowledged != 42
    # The server, on its own, marked an update outstanding (diverged from the
    # empty mirror).
    assert bool(outstanding) is True


def test_divergence_triggers_send_marked_outstanding():
    sim = nrvv_env.Simulation([])
    server = sim.connect(app.Server)

    assert sim.sent == []
    server.submit_desired_price("A", 42)

    # Desired differs from the (empty) mirror -> the server emits exactly once,
    # carrying only (station, price) through the transmit port.
    assert sim.sent == [("A", 42)]
    assert _outstanding(server.get_station_state("A")) is True


def test_acknowledgement_advances_mirror_and_clears_outstanding():
    sim = nrvv_env.Simulation([])
    server = sim.connect(app.Server)

    server.submit_desired_price("A", 42)
    assert sim.sent == [("A", 42)]

    server.acknowledgement_received("A")

    desired, acknowledged, outstanding = _triple(server.get_station_state("A"))
    assert desired == 42
    # The mirror advanced to the acknowledged value.
    assert acknowledged == 42
    # Desired now matches the mirror: nothing outstanding, nothing more sent.
    assert bool(outstanding) is False
    assert sim.sent == [("A", 42)]


def test_latest_desired_wins_with_at_most_one_outstanding():
    sim = nrvv_env.Simulation([])
    server = sim.connect(app.Server)

    server.submit_desired_price("A", 10)
    assert sim.sent == [("A", 10)]

    # A new desired while an update is outstanding must NOT emit a second
    # update (at most one outstanding per station), but updates latest desired.
    server.submit_desired_price("A", 20)
    assert sim.sent == [("A", 10)]
    desired, acknowledged, outstanding = _triple(server.get_station_state("A"))
    assert desired == 20
    assert bool(outstanding) is True

    # Acknowledging the in-flight update: the mirror advances to that
    # acknowledged value (10), which still diverges from desired (20), so the
    # server on its own emits 20 now.
    server.acknowledgement_received("A")
    assert sim.sent == [("A", 10), ("A", 20)]
    desired, acknowledged, outstanding = _triple(server.get_station_state("A"))
    assert acknowledged == 10
    assert desired == 20
    assert bool(outstanding) is True

    # Final acknowledgement: mirror advances to 20, converged, nothing more.
    server.acknowledgement_received("A")
    desired, acknowledged, outstanding = _triple(server.get_station_state("A"))
    assert acknowledged == 20
    assert desired == 20
    assert bool(outstanding) is False
    assert sim.sent == [("A", 10), ("A", 20)]


def test_no_send_when_desired_matches_mirror():
    sim = nrvv_env.Simulation([])
    server = sim.connect(app.Server)

    server.submit_desired_price("A", 50)
    server.acknowledgement_received("A")
    assert sim.sent == [("A", 50)]

    # Re-submitting the already-acknowledged value: desired equals the mirror,
    # so the server suppresses -- no new emission, nothing outstanding.
    server.submit_desired_price("A", 50)
    assert sim.sent == [("A", 50)]
    assert _outstanding(server.get_station_state("A")) is False


def test_state_is_held_per_station_independently():
    sim = nrvv_env.Simulation([])
    server = sim.connect(app.Server)

    server.submit_desired_price("A", 10)
    server.submit_desired_price("B", 99)

    da, aa, outa = _triple(server.get_station_state("A"))
    db, ab, outb = _triple(server.get_station_state("B"))
    assert da == 10 and db == 99
    assert bool(outa) is True and bool(outb) is True

    # Acknowledging A must not touch B's reconciliation state.
    server.acknowledgement_received("A")

    da, aa, outa = _triple(server.get_station_state("A"))
    db, ab, outb = _triple(server.get_station_state("B"))
    assert da == 10 and aa == 10 and bool(outa) is False
    assert db == 99 and bool(outb) is True
    assert ab != 99  # B is still unacknowledged
    assert sim.sent == [("A", 10), ("B", 99)]


def test_server_driven_convergence_regardless_of_station_behaviour():
    for seed in (1, 7, 42, 1234, 99999):
        sim = nrvv_env.Simulation.from_seed(seed, num_stations=3, num_events=20)
        events = list(sim.pending_events)
        server = sim.connect(app.Server)

        sim.run(max_steps=100000)
        assert sim.quiescent()

        # Every emitted update was delivered and acknowledged: the dumb station
        # never rejects an update.
        assert len(sim.sent) == len(sim.delivered) == len(sim.acknowledged)

        # The outbound port carried only (station, price) -- no version/metadata.
        for entry in sim.sent:
            assert isinstance(entry, tuple) and len(entry) == 2

        last_desired = {}
        for s, p in events:
            last_desired[s] = p

        for station, expected in last_desired.items():
            desired, acknowledged, outstanding = _triple(
                server.get_station_state(station))
            # Settled: desired == mirror, nothing outstanding.
            assert desired == expected
            assert acknowledged == expected
            assert bool(outstanding) is False
            # The server's acknowledged mirror matches what the station applied.
            assert sim.applied(station) == expected
