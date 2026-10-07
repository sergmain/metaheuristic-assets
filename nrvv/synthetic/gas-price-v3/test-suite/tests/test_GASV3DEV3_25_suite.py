import app
import nrvv_env
from nrvv_env import Simulation, UNKNOWN


# --------------------------------------------------------------------------
# Helpers: build a fresh server and wire it to a fresh Simulation.
#
# The Interface names operations but not a constructor, so we discover a
# factory/class if the module provides one and otherwise fall back to the
# module itself acting as the server.  In every case the outbound
# send-update port is the Simulation's observable port (both via constructor
# injection, when supported, and via wire_outbound), so every emission the
# server makes is recorded in sim.sent.
# --------------------------------------------------------------------------

_FACTORY_NAMES = (
    "Server", "Service", "App", "Application",
    "make_server", "create_server", "new_server", "build_server",
)


def _new_server(port):
    for name in _FACTORY_NAMES:
        obj = getattr(app, name, None)
        if obj is None:
            continue
        for args in ((), (port,)):
            try:
                return obj(*args)
            except TypeError:
                continue
    # Fall back to the module itself as the server; reset any global state.
    reset = getattr(app, "reset", None)
    if callable(reset):
        try:
            reset()
        except TypeError:
            pass
    return app


def _build(seed, script):
    sim = Simulation(seed=seed, script=script)
    srv = _new_server(sim.outbound)
    sim.attach(srv, wire_outbound=True)
    return sim, srv


def _sent_for(sim, station):
    return [(s, p) for (s, p) in sim.sent if s == station]


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def test_update_addressed_to_station_carries_that_stations_price():
    # Two distinct stations with distinct desired prices.  Driving a
    # transmit for each must hand the send port exactly one update whose
    # station id and single price belong to that station.
    A, B = "stationA", "stationB"
    pA, pB = 111, 222
    for seed in (0, 1, 2):
        sim, _ = _build(seed, script=[(A, pA), (B, pB)])
        sim.fire_submission()   # submit for A -> transmit to A
        sim.fire_submission()   # submit for B -> transmit to B

        assert _sent_for(sim, A) == [(A, pA)]
        assert _sent_for(sim, B) == [(B, pB)]
        # Exactly one update per station, nothing else emitted.
        assert sorted(sim.sent) == sorted([(A, pA), (B, pB)])


def test_single_price_equals_latest_recorded_for_station():
    # One station receives several desired prices; after the first update is
    # acknowledged, the next transmit must carry a single value equal to the
    # LATEST recorded desired price, not an earlier one.
    S = "only-station"
    for seed in (0, 3, 9):
        sim, _ = _build(seed, script=[(S, 100), (S, 200), (S, 300)])
        sim.fire_submission()   # 100 -> transmit (outstanding)
        assert sim.sent == [(S, 100)]

        sim.fire_submission()   # 200 -> pending (update still outstanding)
        sim.fire_submission()   # 300 -> pending, latest recorded
        # No new emission while an update is outstanding.
        assert sim.sent == [(S, 100)]

        outstanding = sim.pending_updates()
        assert len(outstanding) == 1
        assert outstanding[0].station == S
        sim.deliver(outstanding[0].seq)   # station displays 100, acks
        sim.deliver_ack()                 # gate clears -> transmit latest

        last_station, last_price = sim.sent[-1]
        assert last_station == S
        assert last_price == 300


def test_cross_station_updates_do_not_leak():
    # Interleaved submissions for two stations with disjoint price sets.
    # Every update addressed to a station must carry only that station's own
    # prices, and convergence leaves each station at its own latest value.
    A, B = "AA", "BB"
    a_prices = {10, 11}
    b_prices = {98, 99}
    for seed in (0, 1, 5, 13):
        sim, _ = _build(seed, script=[(A, 10), (B, 99), (A, 11), (B, 98)])
        sim.fire_submission()   # A 10 -> transmit
        sim.fire_submission()   # B 99 -> transmit
        sim.fire_submission()   # A 11 -> pending
        sim.fire_submission()   # B 98 -> pending

        # Every emission so far is addressed correctly with its own price.
        for (st, pr) in sim.sent:
            if st == A:
                assert pr in a_prices
            else:
                assert st == B and pr in b_prices

        sim.run()   # drive to quiescence

        # Each station's emissions never carried the other station's price.
        for (st, pr) in sim.sent:
            if st == A:
                assert pr in a_prices
            else:
                assert st == B and pr in b_prices

        # Each converged to its own latest desired price.
        assert _sent_for(sim, A)[-1] == (A, 11)
        assert _sent_for(sim, B)[-1] == (B, 98)
        assert sim.displayed(A) == 11
        assert sim.displayed(B) == 98


def test_targeted_update_is_unaffected_by_another_station():
    # Differential check: a station's emitted update is identical whether or
    # not another station exists and submits around it.
    A, B = "alpha", "beta"
    for seed in (0, 2):
        # Baseline: station A alone.
        base_sim, _ = _build(seed, script=[(A, 42)])
        base_sim.fire_submission()
        baseline = _sent_for(base_sim, A)
        assert baseline == [(A, 42)]

        # Same A submission surrounded by an unrelated station B.
        sim, _ = _build(seed, script=[(B, 7), (A, 42), (B, 8)])
        sim.fire_submission()   # B 7
        sim.fire_submission()   # A 42
        sim.fire_submission()   # B 8

        # A's emission is unchanged by B's presence, price or identifier.
        assert _sent_for(sim, A) == baseline
