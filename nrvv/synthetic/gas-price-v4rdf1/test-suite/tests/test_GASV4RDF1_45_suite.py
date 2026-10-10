'''Tests for GASV4RDF1-17 / GASV4RDF1-45: convergence to the final desired price.'''

import collections

import app
import nrvv_env


MAX_STEPS = 100000
SEEDS = range(25)


def _make_server(send_update, send_pricing_notice):
    return app.Server(send_update, send_pricing_notice)


def _simulation(seed, stations, script=None, clients=3):
    return nrvv_env.Simulation(seed, _make_server, stations, script=script, clients=clients)


def _check_resends_bounded(sim):
    # The server reacts to an acknowledgement within the step that delivers it, and
    # each step is a single event, so the sends at that step are the resends it caused.
    sends_per_step = collections.Counter((sent.step, sent.station) for sent in sim.sent)
    for ack in sim.delivered_acks:
        if ack.price != sim.desired_at(ack.station, ack.step):
            assert sends_per_step[(ack.step, ack.station)] <= 1


def _check_converged(sim):
    for station in sim.station_names:
        desired = sim.latest_desired(station)
        if desired is None:
            continue
        confirmed, current, outstanding = sim.query(station)
        assert current == desired
        assert confirmed == desired
        assert outstanding == 0


def test_run_reaches_quiet_with_no_further_resends():
    for seed in SEEDS:
        sim = _simulation(seed, ['A', 'B', 'C'])
        sim.run(max_steps=MAX_STEPS)
        sent_before = len(sim.sent)
        assert sim.quiet
        assert sim.step() is False
        assert len(sim.sent) == sent_before


def test_each_mismatched_ack_causes_at_most_one_resend():
    for seed in SEEDS:
        sim = _simulation(seed, ['A', 'B', 'C'])
        sim.run(max_steps=MAX_STEPS)
        _check_resends_bounded(sim)


def test_confirmed_price_equals_desired_price_at_end_of_run():
    for seed in SEEDS:
        sim = _simulation(seed, ['A', 'B', 'C'])
        sim.run(max_steps=MAX_STEPS)
        _check_converged(sim)


def test_scripted_repeated_changes_converge():
    script = [
        [('A', 1), ('B', 2), ('A', 3)],
        [('B', 4), ('A', 5), ('B', 6)],
        [('A', 7), ('B', 8)],
    ]
    for seed in SEEDS:
        sim = _simulation(seed, ['A', 'B'], script=script)
        sim.run(max_steps=MAX_STEPS)
        assert sim.quiet
        _check_resends_bounded(sim)
        _check_converged(sim)


def test_confirmed_price_equals_final_desired_once_last_final_update_acked():
    stations = ['A', 'B']
    script = [[('A', 10), ('B', 5), ('A', 20), ('A', 30), ('B', 6), ('A', 40)]]
    for seed in SEEDS:
        sim = _simulation(seed, stations, script=script, clients=1)
        state_after_ack = {}
        steps = 0
        while not sim.quiet:
            if steps >= MAX_STEPS:
                raise AssertionError('not quiet')
            sim.step()
            steps += 1
            if sim.delivered_acks and sim.delivered_acks[-1].step == sim.clock.now:
                ack = sim.delivered_acks[-1]
                state_after_ack[ack.update_id] = sim.query(ack.station)
        for station in stations:
            final = sim.latest_desired(station)
            carrying = [u for u in sim.sent if u.station == station and u.price == final]
            assert carrying
            last = max(carrying, key=lambda u: u.update_id)
            confirmed, desired, _ = state_after_ack[last.update_id]
            assert confirmed == final
            assert desired == final
