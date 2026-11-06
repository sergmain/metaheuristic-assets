"""Tests for GASV3ACC2-33: at most one unacknowledged update per station.

Each test drives the server (``app.Server``) only through the ``nrvv_env``
simulation: producer submits, transport deliveries and acknowledgements all
happen via the simulation's event machinery (``step``/``run``), and everything
asserted comes from the simulation's own observation surface -- the ordered
emit log (``sent``), the in-flight set (``in_flight``) and each modeled
station's applied value (``applied``). The structure of the server's
``get_station_state`` reply is left unspecified by the Interface, so no test
reaches for it; emissions and applied values are enough to witness the
criterion.
"""

import app
import nrvv_env


def _inflight_counts(sim):
    """Updates emitted-but-not-acknowledged, counted per station."""
    counts = {}
    for u in sim.in_flight:
        counts[u.station] = counts.get(u.station, 0) + 1
    return counts


def _sent_count(sim, station):
    """How many updates the server has emitted to ``station`` so far."""
    return sum(1 for (s, _) in sim.sent if s == station)


def test_at_most_one_outstanding_per_station_throughout_run():
    """At no point is a second update emitted to a station that still has an
    unacknowledged one; in particular, submitting a further desired price to a
    station with an outstanding update produces no new emission.
    """
    seeds = [1, 7, 42, 100, 2024]
    saw_further_update_attempt = False
    for seed in seeds:
        sim = nrvv_env.Simulation.from_seed(
            seed, num_stations=2, num_events=40, price_min=1, price_max=5)
        sim.connect(app.Server)
        while True:
            # State observed immediately before the next environment action.
            before_counts = _inflight_counts(sim)
            before_sent = {}
            for (s, _) in sim.sent:
                before_sent[s] = before_sent.get(s, 0) + 1

            action = sim.step()
            if action is None:
                break

            # Core invariant: never more than one update in flight per station.
            for st, c in _inflight_counts(sim).items():
                assert c <= 1, (
                    "station %r had %d updates in flight at once (seed=%r)"
                    % (st, c, seed))

            if action[0] == "submit":
                s = action[1]
                if before_counts.get(s, 0) == 1:
                    # A further update to the station was attempted while its
                    # first update was still unacknowledged. No second update
                    # may be emitted to it now.
                    saw_further_update_attempt = True
                    assert _sent_count(sim, s) == before_sent.get(s, 0), (
                        "server emitted a second update to %r while an earlier "
                        "update was still unacknowledged (seed=%r)"
                        % (s, seed))
        assert sim.quiescent()

    # Guard against a vacuous pass: the suppression situation really arose.
    assert saw_further_update_attempt, (
        "no run ever attempted a further update while one was unacknowledged")


def test_single_station_serializes_and_never_exceeds_one_in_flight():
    """Hammering one station with back-to-back desired prices never puts two
    updates in flight to it, and it ends holding the last update sent.
    """
    events = [("X", v) for v in (11, 22, 33, 44, 55, 66)]
    last = events[-1][1]
    for seed in [0, 1, 2, 3, 4]:
        sim = nrvv_env.Simulation(events, seed=seed)
        sim.connect(app.Server)
        while True:
            action = sim.step()
            if action is None:
                break
            in_flight_to_x = sum(1 for u in sim.in_flight if u.station == "X")
            assert in_flight_to_x <= 1, (
                "two updates were in flight to X at once (seed=%r)" % (seed,))
        assert sim.quiescent()

        sent_prices = [p for (s, p) in sim.sent if s == "X"]
        assert sent_prices, "server never emitted any update to X (seed=%r)" % (seed,)
        # Because only one update is ever in flight, the transport cannot make a
        # superseded value the last applied one.
        assert sent_prices[-1] == last, (
            "last update sent to X was %r, expected %r (seed=%r)"
            % (sent_prices[-1], last, seed))
        assert sim.applied("X") == last, (
            "X holds %r after the final delivery, expected %r (seed=%r)"
            % (sim.applied("X"), last, seed))


def test_final_value_equals_last_update_sent_regardless_of_delivery_order():
    """Under many different transport orderings the station converges to the
    last update the server sent, which is the last desired price it received.
    """
    events = [
        ("A", 10), ("B", 1), ("A", 20), ("C", 7),
        ("B", 2), ("A", 30), ("C", 8), ("B", 3),
        ("A", 40), ("C", 9), ("A", 50), ("B", 4),
    ]
    last_desired = {}
    for (s, p) in events:
        last_desired[s] = p

    for seed in [0, 1, 2, 3, 5, 8, 13, 21]:
        sim = nrvv_env.Simulation(events, seed=seed)
        sim.connect(app.Server)
        sim.run()
        assert sim.quiescent()

        for s, desired in last_desired.items():
            sent_prices = [p for (st, p) in sim.sent if st == s]
            assert sent_prices, "no update ever sent to %r (seed=%r)" % (s, seed)
            # The last update the server actually sent equals the last desired.
            assert sent_prices[-1] == desired, (
                "last update sent to %r was %r, expected last desired %r "
                "(seed=%r)" % (s, sent_prices[-1], desired, seed))
            # And the station holds exactly that after the final delivery,
            # whatever order the transport chose this run.
            assert sim.applied(s) == desired, (
                "station %r applied %r, expected %r (seed=%r)"
                % (s, sim.applied(s), desired, seed))
