import app
from nrvv_env import (
    Simulation, STATIONS, MAX_DELAY, SETTLE_SECONDS,
    price_at_send_violations, unsent_change_violations, convergence_violations,
)

SEEDS = range(1, 21)


def _server_factory(send_price_update):
    servers = [v for name, v in vars(app).items()
               if isinstance(v, type) and name.endswith(('Server', 'Service'))]
    if servers:
        return servers[0](send_price_update)
    app.send_price_update = send_price_update
    return app


def _run(seed):
    sim = Simulation(seed, _server_factory)
    sim.run_until_idle()
    return sim


def _changes(sim, sid):
    return [c for c in sim.changes if c.station == sid]


def test_last_delivered_price_is_latest_desired_price():
    bursts = 0
    checked = 0
    for seed in SEEDS:
        sim = _run(seed)
        for sid in STATIONS:
            changes = _changes(sim, sid)
            if not changes:
                continue
            bursts += sum(1 for a, b in zip(changes, changes[1:]) if b.time - a.time <= MAX_DELAY)
            latest = changes[-1].value
            received = sim.stations[sid].received
            assert received, f'seed {seed} {sid}: no price delivered, latest desired {latest}'
            assert received[-1][1] == latest, f'seed {seed} {sid}: last delivered {received[-1][1]}, latest desired {latest}'
            assert sim.stations[sid].displayed_price == latest, f'seed {seed} {sid}: displays {sim.stations[sid].displayed_price}, latest desired {latest}'
            assert sim.desired_price(sid) == latest, f'seed {seed} {sid}: server desired {sim.desired_price(sid)}, latest {latest}'
            checked += 1
    assert bursts > 0, 'no burst of changes within one transport delay was generated'
    assert checked > 0


def test_last_received_update_is_last_sent_update():
    for seed in SEEDS:
        sim = _run(seed)
        for sid in STATIONS:
            sends = [s for s in sim.sends if s.station == sid]
            if not sends:
                continue
            ids = [s.update_id for s in sends]
            assert ids == sorted(set(ids)), f'seed {seed} {sid}: update ids not strictly increasing {ids}'
            received = sim.stations[sid].received
            assert received[-1][0] == ids[-1], f'seed {seed} {sid}: last received update {received[-1][0]}, last sent {ids[-1]}'


def test_every_change_reaches_station_and_is_sent_at_current_price():
    for seed in SEEDS:
        sim = _run(seed)
        violations = price_at_send_violations(sim)
        assert violations == [], f'seed {seed}: {violations}'
        violations = unsent_change_violations(sim)
        assert violations == [], f'seed {seed}: {violations}'


def test_station_settles_on_latest_price_after_out_of_order_updates():
    for seed in SEEDS:
        sim = _run(seed)
        sim.run_until(sim.now + SETTLE_SECONDS)
        violations = convergence_violations(sim)
        assert violations == [], f'seed {seed}: {violations}'
