'''Suite for GASV4RDF1-43: resends of the desired price are bounded by acknowledgements.'''

import inspect

import app
from nrvv_env import Simulation


STATIONS = ['S1', 'S2']
PRICES = (1, 2, 3)
SEEDS = range(25)
MAX_STEPS = 10000


def _make_server(send_update, send_pricing_notice):
    for value in vars(app).values():
        if inspect.isclass(value) and all(
                callable(getattr(value, name, None))
                for name in ('set_desired_price', 'receive_acknowledgement', 'query_station_state')):
            return value(send_update, send_pricing_notice)
    raise AssertionError('app provides no server class with the Interface operations')


def _run(seed, prices=PRICES, clients=3, calls=10):
    sim = Simulation(seed, _make_server, STATIONS, clients=clients, calls=calls, prices=prices)
    sim.run(max_steps=MAX_STEPS)
    return sim


def _confirmed_before(sim, station, step):
    '''The confirmed price of the station just before the given step, or None.'''
    price = None
    for ack in sim.delivered_acks:
        if ack.step >= step:
            break
        if ack.station == station:
            price = ack.price
    return price


def _outstanding(sim, station, price, step):
    '''Whether an update carrying the price was sent before the step and is not acknowledged by it.'''
    acked = {ack.update_id for ack in sim.delivered_acks if ack.step <= step}
    return any(u.station == station and u.price == price and u.step < step and u.update_id not in acked
               for u in sim.sent)


def _sends(sim, station, price, step):
    '''The updates carrying the price that the server sent to the station at the given step.'''
    return [u for u in sim.sent if u.step == step and u.station == station and u.price == price]


def test_set_desired_price_sends_update_when_price_differs_and_none_outstanding():
    checked = 0
    for seed in SEEDS:
        sim = _run(seed)
        for call in sim.client_calls:
            confirmed = _confirmed_before(sim, call.station, call.step)
            if call.price == confirmed or _outstanding(sim, call.station, call.price, call.step):
                continue
            checked += 1
            assert _sends(sim, call.station, call.price, call.step), (
                f'seed {seed}, step {call.step}: desired {call.price} set on {call.station} '
                f'with confirmed {confirmed} and nothing outstanding, but no update was sent')
    assert checked > 0


def test_ack_leaving_confirmed_different_from_desired_triggers_at_most_one_resend():
    checked = 0
    for seed in SEEDS:
        sim = _run(seed)
        for ack in sim.delivered_acks:
            desired = sim.desired_at(ack.station, ack.step)
            if desired is None or ack.price == desired:
                continue
            checked += 1
            sent = _sends(sim, ack.station, desired, ack.step)
            assert len(sent) <= 1, (
                f'seed {seed}, step {ack.step}: ack {ack.price} on {ack.station} left confirmed '
                f'different from desired {desired}, but {len(sent)} updates carrying it were sent')
    assert checked > 0


def test_no_update_carrying_a_price_is_sent_while_one_with_that_price_is_outstanding():
    checked = 0
    for seed in SEEDS:
        sim = _run(seed)
        for update in sim.sent:
            checked += 1
            assert not _outstanding(sim, update.station, update.price, update.step), (
                f'seed {seed}, step {update.step}: update {update.price} sent to {update.station} '
                f'while an earlier update carrying {update.price} was still outstanding')
    assert checked > 0


def test_ack_confirming_desired_price_triggers_no_further_update_with_that_price():
    checked = 0
    for seed in SEEDS:
        sim = _run(seed)
        for ack in sim.delivered_acks:
            if sim.desired_at(ack.station, ack.step) != ack.price:
                continue
            checked += 1
            sent = _sends(sim, ack.station, ack.price, ack.step)
            assert not sent, (
                f'seed {seed}, step {ack.step}: ack {ack.price} on {ack.station} confirmed the '
                f'desired price, yet an update carrying it was sent')
    assert checked > 0


def test_single_new_desired_price_is_sent_once_when_station_is_idle():
    sim = Simulation(0, _make_server, ['S1'], script=[[('S1', 5)]], clients=1)
    sim.run(max_steps=MAX_STEPS)
    assert [c.price for c in sim.client_calls] == [5]
    call_step = sim.client_calls[0].step
    assert len(_sends(sim, 'S1', 5, call_step)) == 1
    assert [u.price for u in sim.sent].count(5) >= 1


def test_resend_bound_holds_with_wide_price_range():
    checked = 0
    for seed in range(10):
        sim = _run(seed, prices=tuple(range(1, 101)))
        for ack in sim.delivered_acks:
            desired = sim.desired_at(ack.station, ack.step)
            if desired is None or ack.price == desired:
                continue
            checked += 1
            assert len(_sends(sim, ack.station, desired, ack.step)) <= 1, (
                f'seed {seed}, step {ack.step}: more than one resend of {desired} to {ack.station}')
    assert checked > 0
