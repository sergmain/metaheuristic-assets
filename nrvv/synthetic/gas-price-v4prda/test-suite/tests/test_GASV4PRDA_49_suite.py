import app
from nrvv_env import Simulation

CONVERGENCE_BOUND = 60
SEEDS = range(1, 21)


def _last_changes(sim):
    last = {}
    for change in sim.central.changes:
        last[change.station_id] = change
    return last


def _check_convergence(seed, outages):
    sim = Simulation(seed=seed, server=app, outages=outages)
    sim.run_until_idle()
    last = _last_changes(sim)
    if not last:
        return 0, 0
    deadline = max(change.time for change in last.values()) + CONVERGENCE_BOUND
    while sim.now < deadline:
        sim.step()
    checked = 0
    skipped = 0
    for sid, change in sorted(last.items()):
        end = change.time + CONVERGENCE_BOUND
        station = sim.stations[sid]
        if not station.reachable_throughout(change.time, end):
            skipped += 1
            continue
        shown = station.display_at(end)
        assert shown == change.price, (
            f'seed {seed}: station {sid} shows {shown!r} at t={end}, '
            f'latest desired price {change.price!r} was set at t={change.time}'
        )
        checked += 1
    return checked, skipped


def test_latest_price_shown_within_60_seconds_while_reachable():
    checked = 0
    skipped = 0
    for seed in SEEDS:
        seed_checked, seed_skipped = _check_convergence(seed, outages=True)
        checked += seed_checked
        skipped += seed_skipped
    assert checked >= 10, f'only {checked} convergence checks ran ({skipped} skipped)'


def test_latest_price_shown_within_60_seconds_when_always_reachable():
    for seed in SEEDS:
        checked, skipped = _check_convergence(seed, outages=False)
        assert skipped == 0, f'seed {seed}: {skipped} stations were not reachable'
        assert checked > 0, f'seed {seed}: no station had a desired price change'
