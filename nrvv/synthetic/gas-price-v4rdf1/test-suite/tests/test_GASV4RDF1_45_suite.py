import app
from nrvv_env import Simulation

MAX_STEPS = 100000
SEEDS = range(1, 9)


def _scripted_run(seed):
    a, b = 'A%d' % seed, 'B%d' % seed
    script = [(a, 10), (b, 20), (a, 35), (b, 4), (a, 7), (b, 88), (a, 150), (b, 61), (a, 99)]
    sim = Simulation(app, seed, stations=(a, b), script=script)
    sim.run(max_steps=MAX_STEPS)
    return sim, {a: 99, b: 61}


def _state(sim, station):
    state = sim.query(station)
    if isinstance(state, dict):
        return state['confirmed'], state['desired'], state['outstanding']
    confirmed, desired, outstanding = state
    return confirmed, desired, outstanding


def _desired_at(sim, station, step):
    price = None
    for call in sim.call_log:
        if call.station == station and call.step < step:
            price = call.price
    return price


def test_final_desired_price_is_confirmed_after_all_updates_delivered():
    for seed in SEEDS:
        sim, finals = _scripted_run(seed)
        assert sim.is_quiet(), 'seed %d: run did not reach quiet' % seed
        for station, final in finals.items():
            confirmed, desired, outstanding = _state(sim, station)
            assert desired == final
            assert confirmed == final
            assert outstanding == 0
            assert sim.last_ack_price(station) == final


def test_no_resends_once_run_is_quiet():
    for seed in SEEDS:
        sim, _ = _scripted_run(seed)
        sent = len(sim.sent_log)
        acks = len(sim.ack_log)
        assert sim.step() is False
        assert sim.run(max_steps=1000) == 0
        assert len(sim.sent_log) == sent
        assert len(sim.ack_log) == acks


def test_each_mismatching_ack_causes_at_most_one_resend():
    for seed in SEEDS:
        sim, _ = _scripted_run(seed)
        for ack in sim.ack_log:
            if ack.price == _desired_at(sim, ack.station, ack.step):
                continue
            resends = [s for s in sim.sent_log
                       if s.step == ack.step and s.station == ack.station]
            assert len(resends) <= 1


def test_resends_after_last_price_change_bounded_by_later_acks():
    for seed in SEEDS:
        sim, _ = _scripted_run(seed)
        last_call = sim.call_log[-1].step
        later_sends = sum(1 for s in sim.sent_log if s.step > last_call)
        later_acks = sum(1 for a in sim.ack_log if a.step > last_call)
        assert later_sends <= later_acks


def test_random_price_changes_converge_to_final_desired_price():
    for seed in SEEDS:
        sim = Simulation(app, 100 + seed, stations=('X%d' % seed, 'Y%d' % seed),
                         calls=30, prices=(1, 1000))
        sim.run(max_steps=MAX_STEPS)
        assert sim.is_quiet(), 'seed %d: run did not reach quiet' % seed
        for station, desired in sim.desired.items():
            confirmed, state_desired, outstanding = _state(sim, station)
            assert state_desired == desired
            assert confirmed == desired
            assert outstanding == 0
