'''GASV4ELMA-44: convergence bound with no added delay and at most one resend per stale ack.'''
import app
from nrvv_env import Simulation, check

SEEDS = (1, 2, 3, 5, 8, 13, 21, 34)
CONVERGENCE_BOUND = 6.0  # 2 * (D + A) = 2 * (2 + 1) minutes


def _simulation(seed, stations=3):
    sim = Simulation(
        seed=seed,
        server_factory=lambda dispatch: app.Server(dispatch_update=dispatch),
        stations=stations,
    )
    for station_id in sim.station_ids:
        sim.force_reachable(station_id, 0.0)
    return sim


def test_last_change_is_dispatched_in_its_own_step():
    for seed in SEEDS:
        sim = _simulation(seed)
        sim.run()
        last_time, last_station, last_price = sim.price_schedule[-1]
        same_step = [
            r for r in sim.trace
            if r.kind == 'dispatch' and r.station == last_station
            and r.time == last_time and r.price == last_price
        ]
        assert same_step, 'seed %s: latest price %s not dispatched at t=%s' % (seed, last_price, last_time)


def test_every_dispatch_happens_in_step_of_its_trigger():
    for seed in SEEDS:
        sim = _simulation(seed)
        sim.run()
        trigger_time = None
        for r in sim.trace:
            if r.kind in ('set', 'ack', 'reach'):
                trigger_time = r.time
            elif r.kind == 'dispatch':
                assert trigger_time is not None and r.time == trigger_time, (
                    'seed %s: dispatch at t=%s after trigger at t=%s' % (seed, r.time, trigger_time)
                )


def test_each_stale_ack_causes_exactly_one_resend():
    stale_total = 0
    for seed in SEEDS:
        sim = _simulation(seed)
        sim.run()
        trace = sim.trace
        latest = {}
        for i, r in enumerate(trace):
            if r.kind == 'set':
                latest[r.station] = r.price
            elif r.kind == 'ack' and latest.get(r.station) != r.price:
                stale_total += 1
                resends = []
                for later in trace[i + 1:]:
                    if later.kind != 'dispatch':
                        break
                    if later.station == r.station:
                        resends.append(later)
                assert len(resends) == 1, (
                    'seed %s: stale ack at t=%s caused %d resends' % (seed, r.time, len(resends))
                )
                assert resends[0].price == latest[r.station] and resends[0].time == r.time, (
                    'seed %s: resend at t=%s is not the latest price' % (seed, resends[0].time)
                )
    assert stale_total > 0


def test_resends_only_follow_stale_acks():
    for seed in SEEDS:
        sim = _simulation(seed)
        sim.run()
        result = check(sim, convergence_bound=CONVERGENCE_BOUND)
        for key in ('r6_latest_price', 'r4_r5_repeat', 'sequence', 'r7_unreachable_dispatch'):
            assert not result[key], 'seed %s: %s violated: %s' % (seed, key, result[key])


def test_latest_price_converges_within_six_minutes():
    for stations in (1, 3, 5):
        for seed in SEEDS:
            sim = _simulation(seed, stations)
            sim.run()
            result = check(sim, convergence_bound=CONVERGENCE_BOUND)
            failed = {k: v for k, v in result.items() if v}
            assert not failed, 'stations %s seed %s: %s' % (stations, seed, failed)


def test_no_stale_acknowledgement_after_six_minutes():
    for seed in SEEDS:
        sim = _simulation(seed)
        sim.run()
        deadline = sim.convergence_start + CONVERGENCE_BOUND
        final = {}
        for r in sim.trace:
            if r.kind == 'set':
                final[r.station] = r.price
        late = [
            r for r in sim.trace
            if r.kind == 'ack' and r.time > deadline and r.price != final.get(r.station)
        ]
        assert not late, 'seed %s: stale acks after t=%s: %s' % (seed, deadline, late)
