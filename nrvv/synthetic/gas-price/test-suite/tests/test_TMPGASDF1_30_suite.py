"""Tests for TMPGASDF1-30 / TMPGASDF1-3:

At most one unacknowledged price update outstanding per station at any instant.

The service hands each update to the transport through ``send_update`` (logged in
``sim.send_log``) and is told of each acknowledgement through
``receive_acknowledgement`` (logged in ``sim.ack_log`` by the simulation just before
it calls the service).  Therefore, at any instant, the number of updates the service
has sent to a station but not yet had acknowledged is exactly::

    (# of send_log entries for the station) - (# of ack_log entries for the station)

We drive the simulation one event at a time and assert, after every event, that this
count is in {0, 1} for every station.  A buggy service that sent a second update to a
station before the first was acknowledged would push the count to 2 and be caught.

To keep the property non-vacuous (a service that never sends anything trivially keeps
the count at 0), we also assert the service actually sends updates and that runs
converge: each station's displayed price ends equal to its latest desired price with
nothing left outstanding.
"""
import app
from nrvv_env import Simulation


def _outstanding(sim):
    """Outstanding (sent-but-unacknowledged) update count per station."""
    counts = {sid: 0 for sid in sim.station_ids}
    for rec in sim.send_log:
        counts[rec.station] += 1
    for rec in sim.ack_log:
        counts[rec.station] -= 1
    return counts


def _build(seed, **kw):
    sim = Simulation(seed=seed, **kw)
    server = app.Service(sim.send_update)
    sim.connect(server)
    return sim, server


def test_at_most_one_outstanding_per_station_throughout_seeded_runs():
    # Drive several independent seeded runs event by event, checking the invariant
    # after every single event (sends happen synchronously inside an event).
    for seed in (0, 1, 2, 7, 13, 42, 99):
        sim, _server = _build(seed)
        steps = 0
        while True:
            ev = sim.step()
            oc = _outstanding(sim)
            for sid, c in oc.items():
                assert 0 <= c <= 1, (
                    "outstanding count out of range",
                    seed, sid, c, list(sim.send_log), list(sim.ack_log))
            if ev is None:
                break
            steps += 1
            assert steps <= 1000000, ("runaway", seed)
        # non-vacuity: the service really did emit updates in this run
        assert sim.send_log, ("service never sent any update", seed)


def test_at_most_one_outstanding_under_heavier_load():
    # More stations, more and larger bursts -> many coalescing opportunities and
    # more concurrently in-flight updates across stations. Invariant must still hold.
    for seed in (3, 11, 77):
        sim, _server = _build(
            seed, num_stations=6, num_bursts=25, max_burst=5, price_range=(1, 50))
        while True:
            ev = sim.step()
            for sid, c in _outstanding(sim).items():
                assert 0 <= c <= 1, (
                    "outstanding count out of range",
                    seed, sid, c, list(sim.send_log), list(sim.ack_log))
            if ev is None:
                break
        assert sim.send_log, ("service never sent any update", seed)


def test_no_second_update_to_station_while_first_unacknowledged():
    # One desired price -> exactly one update sent to the station.
    sim, _server = _build(0, num_bursts=0)
    sim.inject_desired('S0', 5)
    assert sum(1 for r in sim.send_log if r.station == 'S0') == 1
    assert _outstanding(sim)['S0'] == 1

    # A new desired price arrives before the outstanding update is acknowledged:
    # the service must NOT send a second update to S0 while one is outstanding.
    sim.inject_desired('S0', 11)
    assert sum(1 for r in sim.send_log if r.station == 'S0') == 1, \
        "a second update was sent to S0 while the first was still unacknowledged"
    assert _outstanding(sim)['S0'] == 1

    # Only after the outstanding update is delivered and acknowledged does the next
    # update (reflecting the latest desired price) get sent; the run then converges.
    sim.run()
    assert sim.displayed('S0') == 11
    assert _outstanding(sim)['S0'] == 0


def test_updates_to_different_stations_are_outstanding_independently():
    # A pending update to one station must not block updates to another station:
    # both can be outstanding at the same instant.
    sim, _server = _build(0, num_bursts=0)
    sim.inject_desired('S0', 4)
    sim.inject_desired('S1', 8)
    oc = _outstanding(sim)
    assert oc['S0'] == 1
    assert oc['S1'] == 1  # simultaneously outstanding, independently

    sim.run()
    assert sim.displayed('S0') == 4
    assert sim.displayed('S1') == 8
    assert _outstanding(sim)['S0'] == 0
    assert _outstanding(sim)['S1'] == 0


def test_runs_converge_to_latest_desired_with_nothing_outstanding():
    # Liveness guard for the 'only after an ack does the next update go out' clause:
    # the serialization must still let every station reach its latest desired price.
    for seed in (1, 5, 21, 100):
        sim, _server = _build(seed)
        sim.run()
        assert sim.is_quiescent(), ("did not reach quiescence", seed)

        last_desired = {}
        for rec in sim.input_log:
            last_desired[rec.station] = rec.price
        assert last_desired, ("no inputs issued", seed)

        for sid, price in last_desired.items():
            assert sim.displayed(sid) == price, (
                "station did not converge to latest desired",
                seed, sid, price, sim.displayed(sid))

        for sid, c in _outstanding(sim).items():
            assert c == 0, ("update left outstanding after quiescence", seed, sid, c)
