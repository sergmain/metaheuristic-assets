"""Verifies GASV4ACCJ-5: each reachable station settles on its latest price within 10 minutes.

Drives app only through nrvv_env. For each seed, a station's last planned change is the
latest desired price; the station must be reachable from that change through the
10-minute window, and then the applied price at the deadline must equal that price.
"""

import app
from nrvv_env import Simulation

WINDOW = 600.0
SEEDS = range(1, 21)
STATIONS = ("S1", "S2", "S3")


def _build(seed, prefix):
    # Station names unique per test and seed, so server state from one run does not leak into another.
    stations = tuple(f"{prefix}-{seed}-{name}" for name in STATIONS)
    sim = Simulation(seed, stations=stations)
    sim.connect(app)
    return sim


def _reachable_throughout(sim, station, start, end):
    return not any(s < end and e > start for s, e in sim.unreachable_intervals(station))


def _latest_changes(sim):
    """For each station with at least two planned changes: its last change, the time and the deadline."""
    cases = []
    schedule = sim.schedule()
    for station in sim.stations:
        changes = [(when, price) for when, s, price in schedule if s == station]
        if len(changes) < 2:
            continue
        when, price = changes[-1]
        deadline = when + WINDOW
        if _reachable_throughout(sim, station, when, deadline):
            cases.append((station, when, price, deadline))
    return cases


def test_latest_price_is_applied_ten_minutes_after_last_change():
    checked = 0
    for seed in SEEDS:
        sim = _build(seed, "latest")
        cases = _latest_changes(sim)
        if not cases:
            continue
        sim.run_until(max(deadline for *_, deadline in cases))
        for station, when, price, deadline in cases:
            applied = sim.applied_price(station, at=deadline)
            assert applied == price, (
                f"seed {seed} station {station}: change at {when} to {price}, "
                f"applied at {deadline} is {applied}")
            checked += 1
    assert checked > 0, "no seed produced a reachable latest-change case"


def test_convergence_record_reaches_latest_price_by_deadline():
    checked = 0
    for seed in SEEDS:
        sim = _build(seed, "conv")
        cases = _latest_changes(sim)
        if not cases:
            continue
        sim.run_until(max(deadline for *_, deadline in cases))
        records = sim.convergence()
        for station, when, price, deadline in cases:
            matches = [c for c in records if c.station == station and c.changed_at == when]
            assert len(matches) == 1, f"seed {seed} station {station}: change at {when} not recorded once"
            record = matches[0]
            assert record.price == price
            assert record.converged_at is not None, (
                f"seed {seed} station {station}: price {price} from {when} never applied")
            assert record.converged_at <= deadline, (
                f"seed {seed} station {station}: converged at {record.converged_at}, "
                f"after the 10-minute mark {deadline}")
            checked += 1
    assert checked > 0, "no seed produced a reachable latest-change case"
