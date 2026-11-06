"""Suite for TEST_CASE GASV3ACC2-41 (requirement GASV3ACC2-4).

Criterion: after the update carrying the latest desired price has been sent to a
station, a sequence of updates (including at least one carrying a superseded
price) arrives at that station in an order different from the order the service
sent them; the update the station applies *last* must carry the latest desired
price and must never carry a superseded price value, so the station settles on
the latest desired price regardless of in-transit reordering.

The system is driven only through ``nrvv_env``: desired prices are submitted and
acknowledgements returned through the simulated environment, whose seeded
transport reorders deliveries. The last price a station applies is observed via
the environment's station model (``sim.applied`` / ``sim.delivered``).
"""

import collections

import app
import nrvv_env


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _latest_desired(events):
    """Per station, the last desired price submitted (the latest desired)."""
    latest = {}
    for station, price in events:
        latest[station] = price
    return latest


def _superseded_values(events):
    """Per station, the set of earlier desired prices whose value differs from
    the latest desired price -- i.e. the values that are outdated once the
    latest desired price exists."""
    seq = collections.defaultdict(list)
    for station, price in events:
        seq[station].append(price)
    sup = {}
    for station, prices in seq.items():
        final = prices[-1]
        sup[station] = set(v for v in prices[:-1] if v != final)
    return sup


def _delivered_by_station(sim):
    """The ordered list of prices each station actually applied."""
    by_station = collections.defaultdict(list)
    for station, price in sim.delivered:
        by_station[station].append(price)
    return by_station


def _drive(events, seed, max_steps=200000):
    """Build a simulation over an explicit producer sequence, wire the server to
    the transport, and drive it to quiescence under the given transport seed."""
    sim = nrvv_env.Simulation(events, seed=seed)
    sim.connect(app.Server)
    sim.run(max_steps=max_steps)
    return sim


# A scenario in which the target station S0 receives three distinct desired
# prices (10, 20, 30); 30 is the latest desired and 10/20 are superseded.
# A second station S1 runs interleaved so the transport has concurrent
# in-flight updates to reorder.
_CRAFTED = [
    ("S0", 10),
    ("S1", 5),
    ("S0", 20),
    ("S1", 6),
    ("S0", 30),
    ("S1", 7),
]

_CRAFTED_SEEDS = range(0, 25)


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #

def test_last_applied_update_carries_latest_desired_price():
    """The last update every station applies carries that station's latest
    desired price, across many transport orderings."""
    latest = _latest_desired(_CRAFTED)
    for seed in _CRAFTED_SEEDS:
        sim = _drive(_CRAFTED, seed)
        assert sim.quiescent(), "seed %r did not drain" % (seed,)
        by_station = _delivered_by_station(sim)
        for station, want in latest.items():
            applied_seq = by_station.get(station)
            assert applied_seq, "station %r received nothing (seed %r)" % (
                station, seed)
            # The update applied last is the final element of its delivery log.
            assert applied_seq[-1] == want, (
                "seed %r station %r: last applied %r != latest desired %r"
                % (seed, station, applied_seq[-1], want))
            # And the station's settled applied value agrees.
            assert sim.applied(station) == want, (
                "seed %r station %r: settled on %r != latest desired %r"
                % (seed, station, sim.applied(station), want))


def test_last_applied_update_is_never_a_superseded_value():
    """The last value a station applies is never one of its superseded prices."""
    latest = _latest_desired(_CRAFTED)
    sup = _superseded_values(_CRAFTED)
    for seed in _CRAFTED_SEEDS:
        sim = _drive(_CRAFTED, seed)
        assert sim.quiescent()
        by_station = _delivered_by_station(sim)
        for station in latest:
            last_applied = by_station[station][-1]
            assert last_applied not in sup[station], (
                "seed %r station %r settled on superseded value %r"
                % (seed, station, last_applied))
            assert last_applied == latest[station]


def test_superseded_price_arrives_yet_station_settles_on_latest():
    """At least one superseded price actually arrives at the station, and yet
    the update it applies last still carries the latest desired price -- the
    exact situation the requirement guards against."""
    latest = _latest_desired(_CRAFTED)
    sup = _superseded_values(_CRAFTED)
    for seed in _CRAFTED_SEEDS:
        sim = _drive(_CRAFTED, seed)
        assert sim.quiescent()
        applied_seq = _delivered_by_station(sim)["S0"]
        # A superseded value (e.g. the first, 10) really was delivered.
        assert any(v in sup["S0"] for v in applied_seq), (
            "seed %r: no superseded price ever reached S0 (%r)"
            % (seed, applied_seq))
        # The last update applied carries the latest desired price.
        assert applied_seq[-1] == latest["S0"]


def test_in_transit_reordering_occurs_but_station_still_settles():
    """Across the seeds, the transport delivers updates in an order different
    from the order the service sent them (reordering is real, not assumed); in
    every such run the station still settles on the latest desired price."""
    latest = _latest_desired(_CRAFTED)
    reordered_any = False
    for seed in _CRAFTED_SEEDS:
        sim = _drive(_CRAFTED, seed)
        assert sim.quiescent()
        if list(sim.sent) != list(sim.delivered):
            reordered_any = True
        by_station = _delivered_by_station(sim)
        for station, want in latest.items():
            assert by_station[station][-1] == want
            assert sim.applied(station) == want
    assert reordered_any, (
        "no seed produced an in-transit reordering; premise not exercised")


def test_settlement_under_seeded_producer_sequences():
    """Broader property check: for seeded producer sequences (which include
    stations that receive several, superseded, desired prices), every station's
    last applied update carries its latest desired price."""
    for seed in range(0, 40):
        sim = nrvv_env.Simulation.from_seed(
            seed, num_stations=4, num_events=30, price_min=1, price_max=20)
        events = list(sim.pending_events)      # full producer sequence
        latest = _latest_desired(events)
        sim.connect(app.Server)
        sim.run(max_steps=500000)
        assert sim.quiescent(), "seed %r did not drain" % (seed,)
        by_station = _delivered_by_station(sim)
        for station, want in latest.items():
            applied_seq = by_station.get(station)
            assert applied_seq, "station %r received nothing (seed %r)" % (
                station, seed)
            assert applied_seq[-1] == want, (
                "seed %r station %r: last applied %r != latest desired %r"
                % (seed, station, applied_seq[-1], want))
            assert sim.applied(station) == want
