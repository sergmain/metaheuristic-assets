"""Suite for TEST_CASE GASV3ACC2-31.

Criterion: while an earlier update to a station remains unacknowledged the
service sends no new price to it; the instant the station has no earlier update
outstanding and its latest desired price differs from the price it most recently
acknowledged, the service transmits exactly that latest desired price to that
station immediately, with no further delay; if the latest desired equals the
most recently acknowledged price, nothing is sent.

Everything is observed through the `nrvv_env` simulation only: the outbound
transmit port (GASV3ACC2-16) feeds `sim.sent`, the in-flight (emitted but not
yet acknowledged) updates are `sim.in_flight`, and each atomic environment
action returned by `sim.step()` lets us track, exactly, each station's latest
desired price and most recently acknowledged price.
"""

import app
import nrvv_env


SEEDS = [1, 2, 3, 7, 13, 42, 100, 2024]


def _make_server(sim):
    """Build `app`'s server with its outbound transmit port (GASV3ACC2-16)
    wired to the simulation, and bind it so the simulation can drive it."""
    if hasattr(app, "Server"):
        return sim.connect(app.Server)
    for name in ("Service", "create_server", "make_server", "build_server",
                 "new_server"):
        obj = getattr(app, name, None)
        if obj is not None:
            server = sim.connect(obj) if callable(obj) else sim.bind(obj)
            return server
    for setter in ("set_transmit", "bind_transmit", "configure", "wire"):
        fn = getattr(app, setter, None)
        if fn is not None:
            fn(sim.transmit)
            sim.bind(app)
            return app
    raise AssertionError("cannot construct the app server for testing")


def _trace(sim):
    """Drive the simulation to quiescence, recording one snapshot after each
    atomic action. Each snapshot carries, as of that moment: the per-station
    count of outstanding (in-flight) updates, each station's latest desired and
    most recently acknowledged price, and any prices newly transmitted during
    the action (paired with the latest desired price at that moment)."""
    desired = {}
    acked = {}
    prev = 0
    snaps = []
    while True:
        action = sim.step()
        if action is None:
            break
        if action[0] == "submit":
            desired[action[1]] = action[2]
        elif action[0] == "ack":
            u = action[1]
            acked[u.station] = u.price

        new = sim.sent[prev:]
        prev = len(sim.sent)

        counts = {}
        for u in sim.in_flight:
            counts[u.station] = counts.get(u.station, 0) + 1

        snaps.append({
            "kind": action[0],
            "counts": counts,
            "desired": dict(desired),
            "acked": dict(acked),
            "new_sends": [(s, p, desired.get(s)) for (s, p) in new],
        })
    return snaps


def test_no_new_price_while_prior_update_unacknowledged():
    # At most one update per station may be outstanding at any instant: if the
    # service sent a new price while an earlier one was still unacknowledged,
    # two of that station's updates would be in flight simultaneously.
    for seed in SEEDS:
        sim = nrvv_env.Simulation.from_seed(seed)
        _make_server(sim)
        for snap in _trace(sim):
            for station, count in snap["counts"].items():
                assert count <= 1, (
                    "seed %r: station %r had %d updates outstanding; a new "
                    "price was sent while an earlier update was unacknowledged"
                    % (seed, station, count))


def test_latest_price_sent_immediately_when_idle_and_diverged():
    # The only legitimate state for an idle station (no outstanding update) is
    # one in which its latest desired price already equals its most recently
    # acknowledged price. Any divergence on an idle station means the service
    # failed to transmit the latest desired price immediately (with no further
    # delay) the moment the station became free.
    for seed in SEEDS:
        sim = nrvv_env.Simulation.from_seed(seed)
        _make_server(sim)
        for snap in _trace(sim):
            for station, want in snap["desired"].items():
                idle = snap["counts"].get(station, 0) == 0
                if idle:
                    assert want == snap["acked"].get(station), (
                        "seed %r: station %r is idle with latest desired %r but "
                        "last acknowledged %r -- the latest price was not "
                        "transmitted immediately"
                        % (seed, station, want, snap["acked"].get(station)))


def test_transmitted_price_equals_latest_desired():
    # Every transmission carries exactly the station's latest desired price at
    # the moment of sending (intermediate values are coalesced away, never a
    # stale value), and transmissions do actually occur in these runs.
    for seed in SEEDS:
        sim = nrvv_env.Simulation.from_seed(seed)
        _make_server(sim)
        total = 0
        for snap in _trace(sim):
            for (station, price, want) in snap["new_sends"]:
                total += 1
                assert price == want, (
                    "seed %r: transmitted price %r to station %r but its latest "
                    "desired price was %r" % (seed, price, station, want))
        assert total > 0, "seed %r exercised no transmissions" % (seed,)


def test_equal_price_is_not_transmitted():
    # Submitting the same price repeatedly must yield exactly one transmission:
    # once the station has acknowledged that value, latest desired equals most
    # recently acknowledged, so nothing further is sent regardless of ordering.
    for seed in [0, 1, 5, 9, 17]:
        sim = nrvv_env.Simulation([("S0", 50), ("S0", 50), ("S0", 50)], seed=seed)
        _make_server(sim)
        _trace(sim)
        sends = [p for (s, p) in sim.sent if s == "S0"]
        assert sends == [50], (
            "seed %r: expected a single transmission [50], got %r"
            % (seed, sends))


def test_change_then_noop_resubmit_sends_only_the_change():
    # First value is sent (idle at submit), the later distinct value is sent
    # once the first is acknowledged, and the trailing resubmission of that same
    # value (now equal to what was acknowledged) is not retransmitted.
    for seed in [0, 2, 4, 6, 11, 23]:
        sim = nrvv_env.Simulation([("S0", 7), ("S0", 9), ("S0", 9)], seed=seed)
        _make_server(sim)
        _trace(sim)
        sends = [p for (s, p) in sim.sent if s == "S0"]
        assert sends == [7, 9], (
            "seed %r: expected transmissions [7, 9], got %r" % (seed, sends))


def test_converges_to_latest_desired():
    # Consequence of sending the latest price at the earliest permissible
    # moment: once quiescent, every station's most recently acknowledged price
    # equals its latest desired price, and the station holds that value.
    for seed in SEEDS:
        sim = nrvv_env.Simulation.from_seed(seed)
        _make_server(sim)
        snaps = _trace(sim)
        assert sim.quiescent(), "seed %r did not reach quiescence" % (seed,)
        final = snaps[-1]
        for station, want in final["desired"].items():
            assert final["acked"].get(station) == want, (
                "seed %r: station %r settled at acknowledged %r, latest desired %r"
                % (seed, station, final["acked"].get(station), want))
            assert sim.applied(station) == want, (
                "seed %r: station %r applied %r, latest desired %r"
                % (seed, station, sim.applied(station), want))
