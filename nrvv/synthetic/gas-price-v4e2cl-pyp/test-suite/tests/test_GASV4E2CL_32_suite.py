'''GASV4E2CL-32: convergence is achieved against unchanged stations, using only the
existing price update and acknowledgement message types (GASV4E2CL-9).'''
import app
from nrvv_env import (
    Simulation, STATIONS, DURATION,
    convergence_violations, message_form_violations, unsent_change_violations,
)

SEEDS = (1, 2, 3, 4, 5)
CHECK_EVERY = 600
END = DURATION + 2 * 3600


def _make_server(send_price_update):
    '''Builds app's server class: the one taking the send port and exposing set_desired_price.'''
    for name in sorted(dir(app)):
        cls = getattr(app, name)
        if not (isinstance(cls, type) and name[:1].isupper() and hasattr(cls, 'set_desired_price')):
            continue
        try:
            return cls(send_price_update)
        except TypeError:
            return cls()
    raise AssertionError('app has no server class with set_desired_price')


def _run(seed):
    '''Runs the convergence scenario for one seed; returns the simulation and the
    convergence violations seen at every checkpoint.'''
    sim = Simulation(seed, lambda send: _make_server(send))
    violations = []
    for t in range(CHECK_EVERY, END + 1, CHECK_EVERY):
        sim.run_until(t)
        violations += convergence_violations(sim)
    return sim, violations


def test_every_station_converges_with_unchanged_stations():
    for seed in SEEDS:
        sim, violations = _run(seed)
        assert sim.changes and sim.sends, f'seed {seed}: scenario produced no price traffic'
        assert not violations, f'seed {seed}: ' + '; '.join(violations[:5])


def test_convergence_is_tested_under_station_outages():
    for seed in SEEDS:
        sim, _ = _run(seed)
        assert any(sim.outages(sid, until=END) for sid in STATIONS), f'seed {seed}: no station outage occurred'


def test_every_price_change_reaches_its_station():
    for seed in SEEDS:
        sim, _ = _run(seed)
        violations = unsent_change_violations(sim, until=END)
        assert not violations, f'seed {seed}: ' + '; '.join(violations[:5])


def test_only_existing_price_update_and_ack_types_on_station_interface():
    for seed in SEEDS:
        sim, _ = _run(seed)
        assert sim.to_station and sim.from_station, f'seed {seed}: no station traffic'
        assert {m.kind for m in sim.to_station} == {'update'}, f'seed {seed}: custom message sent to a station'
        assert {m.kind for m in sim.from_station} == {'ack'}, f'seed {seed}: custom message from a station'
        assert not message_form_violations(sim), f'seed {seed}'


def test_station_receives_only_sent_price_updates():
    for seed in SEEDS:
        sim, _ = _run(seed)
        sent = {(s.station, s.update_id, s.price) for s in sim.sends}
        for sid, station in sim.stations.items():
            for update_id, price in station.received:
                assert (sid, update_id, price) in sent, f'seed {seed}: {sid} got unsent update {update_id}'
            if station.received:
                assert station.displayed_price == station.received[-1][1], f'seed {seed}: {sid} display mismatch'
        delivered = [m for m in sim.to_station if m.delivered_at is not None]
        received = sum(len(st.received) for st in sim.stations.values())
        assert len(delivered) == received, f'seed {seed}: delivered {len(delivered)}, received {received}'
