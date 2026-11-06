'''GASV4ACCJ-37: each reachable station settles on its latest desired price within 10 minutes.

Drives app only through nrvv_env. Every run uses fixed seeds; there is no clock and no thread.
'''

import app
from nrvv_env import Simulation

SEEDS = range(1, 13)
SETTLE_WINDOW = 600


def _server(ports):
    # The server under test receives the ports object so it can send updates and acknowledgements.
    make = getattr(app, 'create_server', None) or getattr(app, 'PricingServer', None)
    if make is not None:
        return make(ports)
    connect = getattr(app, 'connect', None)
    if connect is None:
        raise AssertionError('app exposes neither a server factory nor connect(ports)')
    connect(ports)
    return app


def _run(seed, loss_rate=0.1):
    '''Run the simulation until every change has been dispatched and every settle window has elapsed.

    Returns the simulation and, per station, the price applied at each simulated second.
    '''
    sim = Simulation(seed, _server, loss_rate=loss_rate)
    applied = {sid: {} for sid in sim.stations}
    while True:
        t = sim.step()
        for sid in applied:
            applied[sid][t] = sim.applied_price(sid)
        if t > sim.horizon + 3600:
            raise AssertionError('simulation did not settle within the reachability tail (seed %d)' % seed)
        if sim.pending_changes() == 0:
            last_changes = [sim.convergence(sid)[-1][0] for sid in applied if sim.convergence(sid)]
            if last_changes and t >= max(last_changes) + SETTLE_WINDOW:
                break
    return sim, applied


def _settle_candidates(sim):
    '''Last desired change per station, kept only when the station stays reachable through its 10-minute window.'''
    candidates = []
    for sid in sim.stations:
        history = sim.convergence(sid)
        if not history:
            continue
        when, price, _ = history[-1]
        window = range(when, when + SETTLE_WINDOW + 1)
        if all(sim.is_reachable(sid, t) for t in window):
            earlier = {entry[1] for entry in history[:-1]}
            candidates.append((sid, when, price, earlier))
    return candidates


def test_latest_price_applied_within_10_minutes_when_reachable():
    checked = 0
    for seed in SEEDS:
        sim, applied = _run(seed)
        for sid, when, price, _ in _settle_candidates(sim):
            deadline = when + SETTLE_WINDOW
            reported = applied[sid][deadline]
            assert reported == price, (
                'seed %d station %s: at %d s the applied price is %r, latest desired is %r (changed at %d s)'
                % (seed, sid, deadline, reported, price, when))
            converged_at = sim.convergence(sid)[-1][2]
            assert converged_at is not None and converged_at <= deadline, (
                'seed %d station %s: latest price %r reached at %r, after the 10-minute mark %d'
                % (seed, sid, price, converged_at, deadline))
            checked += 1
    assert checked >= 10, 'too few reachable settle windows were exercised (%d)' % checked


def test_latest_price_applied_within_10_minutes_without_loss():
    checked = 0
    for seed in SEEDS:
        sim, applied = _run(seed, loss_rate=0.0)
        for sid, when, price, _ in _settle_candidates(sim):
            deadline = when + SETTLE_WINDOW
            assert applied[sid][deadline] == price, (
                'seed %d station %s (no loss): applied %r at %d s, latest desired %r'
                % (seed, sid, applied[sid][deadline], deadline, price))
            checked += 1
    assert checked >= 10, 'too few reachable settle windows were exercised (%d)' % checked


def test_price_returned_to_earlier_value_settles_on_latest():
    checked = 0
    for seed in SEEDS:
        sim, applied = _run(seed)
        for sid, when, price, earlier in _settle_candidates(sim):
            if not earlier:
                continue
            deadline = when + SETTLE_WINDOW
            assert applied[sid][deadline] == price, (
                'seed %d station %s: station reverted to an earlier price, applied %r at %d s, latest %r'
                % (seed, sid, applied[sid][deadline], deadline, price))
            checked += 1
    assert checked >= 1, 'no reachable case with an earlier price in the history was exercised'
