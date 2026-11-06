"""Suite for GASV3ACC2-34.

Criterion: model each station as a dumb applier that blindly applies every
update it receives in the order received -- no stored version data, no price
comparison, no rejection of duplicate/outdated updates. Drive the service with
an arbitrary sequence of desired-price changes per station, let it deliver, and
after delivery settles each station's applied price must equal its *latest*
desired price. A station ending on a stale value, or convergence that would
require the station to version/compare/discard, is a failure.

The modeled ``nrvv_env.Station`` is already a version-free blind applier
(it overwrites its one slot on every delivery, never rejects, never dedupes),
and the outbound transmit port carries only (station, price) -- no version or
sequence metadata. So if convergence to the latest desired price still happens
when every emitted update is blindly applied, the obligation is met entirely by
the service, which is exactly what the requirement demands.

The server (`app`) is wired by handing it the simulation's transmit port, per
the environment's documented ``connect`` convention.
"""

from collections import Counter

import app
import nrvv_env


# Several fixed seeds per property (deterministic: no clock, no threads).
SEEDS = [0, 1, 2, 3, 7, 13, 42, 1234, 2024, 99999]

# Generous ceiling so a non-converging / infinitely-re-emitting implementation
# fails loudly via the quiescence assertion instead of hanging the suite.
MAX_STEPS = 200000


def _latest_desired(events):
    """Map each station to the price of its last desired-price change."""
    latest = {}
    for station, price in events:
        latest[station] = price
    return latest


def _drive(sim):
    """Wire `app`'s server to the simulation and run until quiescent."""
    sim.connect(app.Server)
    sim.run(max_steps=MAX_STEPS)
    return sim


def test_seeded_runs_settle_each_station_on_latest_desired():
    for seed in SEEDS:
        sim = nrvv_env.Simulation.from_seed(
            seed, num_stations=4, num_events=30, price_min=1, price_max=50
        )
        # Full producer sequence is known before anything is submitted.
        desired = _latest_desired(list(sim.pending_events))

        _drive(sim)

        assert sim.quiescent(), "seed %r did not settle" % (seed,)
        for station, price in desired.items():
            assert sim.applied(station) == price, (
                "seed %r station %r ended on %r, latest desired was %r"
                % (seed, station, sim.applied(station), price)
            )


def test_settles_despite_duplicate_and_decreasing_desired_prices():
    # Deliberate duplicates and non-monotonic (decreasing / repeated) changes:
    # a station that compared values or discarded "stale"/duplicate updates
    # could get stuck on a wrong value. The final applied price must be the
    # LAST desired price, never an intermediate high or a duplicate.
    events = [
        ("A", 50), ("A", 50), ("A", 10), ("B", 99), ("A", 10),
        ("B", 1), ("A", 73), ("B", 1), ("C", 5), ("C", 5),
        ("A", 42), ("B", 100), ("C", 5), ("A", 42), ("B", 7),
    ]
    desired = _latest_desired(events)  # A->42, B->7, C->5

    for seed in SEEDS:
        sim = nrvv_env.Simulation(events, seed=seed)

        _drive(sim)

        assert sim.quiescent(), "seed %r did not settle" % (seed,)
        for station, price in desired.items():
            assert sim.applied(station) == price, (
                "seed %r station %r ended on stale %r, latest desired %r"
                % (seed, station, sim.applied(station), price)
            )


def test_single_station_high_churn_ends_on_last_value():
    # Heavy churn on one station: many rapid desired-price changes, including
    # repeats and ups/downs. The blind applier must end on the final value.
    churn = [37, 37, 2, 99, 99, 5, 61, 61, 8, 8, 44, 3, 3, 76, 76, 12]
    events = [("ONLY", p) for p in churn]

    for seed in SEEDS:
        sim = nrvv_env.Simulation(events, seed=seed)

        _drive(sim)

        assert sim.quiescent(), "seed %r did not settle" % (seed,)
        assert sim.applied("ONLY") == churn[-1], (
            "seed %r ended on %r, latest desired %r"
            % (seed, sim.applied("ONLY"), churn[-1])
        )


def test_station_blindly_applies_every_update_none_discarded():
    # The requirement forbids relying on the station to discard anything. Prove
    # the station really is a blind applier under these runs: every emitted
    # update is delivered and applied (nothing lost, nothing added, nothing
    # deduped), and per station the delivery order matches the emission order.
    for seed in SEEDS:
        sim = nrvv_env.Simulation.from_seed(
            seed, num_stations=3, num_events=25, price_min=1, price_max=20
        )

        _drive(sim)

        assert sim.quiescent(), "seed %r did not settle" % (seed,)

        # Nothing discarded or fabricated at the transport/station boundary.
        assert Counter(sim.delivered) == Counter(sim.sent)
        assert Counter(sim.acknowledged) == Counter(sim.sent)

        # Every delivered update was blindly applied (no rejection/dedup).
        total_applied = sum(st.received_count for st in sim.stations.values())
        assert total_applied == len(sim.sent) == len(sim.delivered)

        # Per station the blind applier sees updates in emission order.
        for station in sim.stations:
            sent_seq = [p for (st, p) in sim.sent if st == station]
            delivered_seq = [p for (st, p) in sim.delivered if st == station]
            assert delivered_seq == sent_seq


def test_last_emitted_per_station_equals_latest_desired():
    # Convergence is carried entirely by the service: for every station it
    # must have emitted its latest desired price as the last update (so the
    # blind applier's final overwrite lands on the right value).
    for seed in SEEDS:
        sim = nrvv_env.Simulation.from_seed(
            seed, num_stations=5, num_events=40, price_min=1, price_max=30
        )
        desired = _latest_desired(list(sim.pending_events))

        _drive(sim)

        assert sim.quiescent(), "seed %r did not settle" % (seed,)
        for station, price in desired.items():
            sent_seq = [p for (st, p) in sim.sent if st == station]
            assert sent_seq, (
                "seed %r station %r never received any update" % (seed, station)
            )
            assert sent_seq[-1] == price, (
                "seed %r station %r last emitted %r, latest desired %r"
                % (seed, station, sent_seq[-1], price)
            )
            assert sim.applied(station) == price
