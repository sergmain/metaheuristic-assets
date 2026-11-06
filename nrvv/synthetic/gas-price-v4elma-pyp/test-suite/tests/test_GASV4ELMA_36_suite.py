"""GASV4ELMA-36: a reachability change must read back and dispatch the latest update (GASV4ELMA-16)."""
import app
from nrvv_env import Simulation, check

SEEDS = tuple(range(1, 9))


def _server(dispatch):
    return app.Server(dispatch_update=dispatch)


def _field(state, *names):
    for name in names:
        if isinstance(state, dict) and name in state:
            return state[name]
        if hasattr(state, name):
            return getattr(state, name)
    raise AssertionError('station state %r has none of the fields %s' % (state, names))


def _run_stepwise(seed, observe):
    sim = Simulation(seed=seed, server_factory=_server, stations=3)
    while True:
        before = len(sim.trace)
        if not sim.step():
            return sim
        observe(sim, sim.trace[before:])


def _reconnect_dispatches(trace):
    """Check every reconnection in trace; return how many dispatched the retained latest value."""
    reachable, latest, last_sent, changed_while_down = {}, {}, {}, {}
    dispatched_on_reconnect = 0
    for i, r in enumerate(trace):
        if r.kind == 'set':
            latest[r.station] = r.price
            if not reachable.get(r.station, True):
                changed_while_down[r.station] = True
        elif r.kind == 'dispatch':
            last_sent[r.station] = r.price
        elif r.kind == 'reach':
            reachable[r.station] = r.detail
            if r.detail:
                changed = changed_while_down.pop(r.station, False)
                block = []
                j = i + 1
                while (j < len(trace) and trace[j].kind == 'dispatch'
                       and trace[j].station == r.station and trace[j].time == r.time):
                    block.append(trace[j])
                    j += 1
                want = 1 if changed and latest[r.station] != last_sent.get(r.station) else 0
                assert len(block) == want, (
                    'reconnect of %s at t=%s: expected %d dispatch(es), got %d'
                    % (r.station, r.time, want, len(block)))
                assert all(d.price == latest[r.station] for d in block), (
                    'reconnect of %s at t=%s dispatched a non-latest price' % (r.station, r.time))
                dispatched_on_reconnect += want
    return dispatched_on_reconnect


def _observe_reachable_flag(sim, new):
    for r in new:
        if r.kind == 'reach':
            state = sim.app.station_state(r.station)
            assert _field(state, 'reachable') == r.detail, (
                'after reach %s at t=%s the reachable state does not read %s' % (r.station, r.time, r.detail))


def _observe_outage(sim, new):
    for r in new:
        if r.kind == 'reach' and not r.detail:
            state = sim.app.station_state(r.station)
            assert not _field(state, 'reachable'), (
                'reachable state still reads true after drop of %s at t=%s' % (r.station, r.time))
        if r.kind == 'dispatch':
            assert sim.stations[r.station].reachable, (
                'dispatch to unreachable %s at t=%s' % (r.station, r.time))


def test_reconnect_reads_reachable_true_and_dispatches_latest_only_when_changed():
    total = 0
    for seed in SEEDS:
        sim = _run_stepwise(seed, _observe_reachable_flag)
        total += _reconnect_dispatches(sim.trace)
    assert total > 0, 'no reconnection dispatched a value changed while the station was down'


def test_unreachable_reads_false_and_no_dispatch_reaches_station():
    for seed in SEEDS:
        _run_stepwise(seed, _observe_outage)


def test_set_while_unreachable_is_retained_and_not_dispatched():
    seen = [0]

    def observe(sim, new):
        for r in new:
            if r.kind == 'set' and not sim.stations[r.station].reachable:
                state = sim.app.station_state(r.station)
                assert _field(state, 'latestDesired', 'latest_desired') == r.price, (
                    'latest desired value not retained while %s is unreachable' % (r.station,))
                assert not any(d.kind == 'dispatch' and d.station == r.station for d in new), (
                    'dispatch to %s while unreachable' % (r.station,))
                seen[0] += 1

    for seed in SEEDS:
        _run_stepwise(seed, observe)
    assert seen[0] > 0, 'no set happened while a station was unreachable'


def test_oracle_checks_pass_after_reachability_churn():
    for seed in SEEDS:
        sim = Simulation(seed=seed, server_factory=_server, stations=3)
        sim.run()
        violations = check(sim)
        assert not any(violations.values()), (seed, {k: v[:3] for k, v in violations.items() if v})
