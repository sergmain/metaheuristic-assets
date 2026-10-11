'''GASV4ACCJ-33: the send decision is taken at every trigger; a send is issued only when it is due.'''

import app
from nrvv_env import Simulation

ABANDON_AFTER = 30.0
LIMIT = 2400.0
MAX_EVENTS = 20000


def _outstanding(sends, station, now):
    '''Sends the server still counts as outstanding: unacknowledged and not yet abandoned.'''
    return [
        r for r in sends
        if r.station == station
        and (r.state in ('in_transit', 'delivered')
             or (r.state == 'dropped' and now - r.sent_at < ABANDON_AFTER))
    ]


def _held(acks, station):
    held = None
    for record in acks:
        if record.station == station:
            held = record.price
    return held


def _sends_to(sim, station):
    return [r for r in sim.sends() if r.station == station]


def _arrangement(desired, held, in_flight_prices):
    if desired is None:
        return None
    if desired == held:
        return 'equal'
    if desired in in_flight_prices:
        return 'in_flight'
    if not in_flight_prices:
        return 'send'
    return None  # another price is in flight; the requirement does not decide this case


def _check_every_trigger(sim, seen):
    for _ in range(MAX_EVENTS):
        if sim.now > LIMIT:
            return
        changes, acks = len(sim.changes()), len(sim.acks())
        deliveries, sends = len(sim.deliveries()), len(sim.sends())
        if not sim.step():
            return
        now = sim.now
        earlier = sim.sends()[:sends]
        new_sends = sim.sends()[sends:]
        if len(sim.changes()) > changes:
            trigger, stations = 'price change', [sim.changes()[-1].station]
        elif len(sim.acks()) > acks:
            trigger, stations = 'acknowledgement', [sim.acks()[-1].station]
        elif len(sim.deliveries()) > deliveries:
            assert not new_sends, 'a send was issued on a delivery, which is not a trigger'
            continue
        else:
            trigger, stations = 'due time or abandonment', list(sim.stations)
        for station in stations:
            desired = sim.desired_price(station)
            held = _held(sim.acks(), station)
            in_flight = [r.price for r in _outstanding(earlier, station, now)]
            arrangement = _arrangement(desired, held, in_flight)
            if arrangement is None:
                continue
            seen.add(arrangement)
            issued = [r for r in new_sends if r.station == station]
            if arrangement == 'send':
                assert len(issued) == 1 and issued[0].price == desired, (
                    f'{trigger} at {now}: expected one send of {desired}, '
                    f'got {[r.price for r in issued]}')
            else:
                assert not issued, (
                    f'{trigger} at {now}: arrangement {arrangement} must send nothing, '
                    f'got {len(issued)} send(s)')
    raise AssertionError('simulation did not finish')


def _single_change_sim(tag, drop_probability):
    '''A connected run whose only planned price change is the first one; returns (sim, station, price, time).'''
    for seed in range(1000):
        name = f'{tag}-{seed}'
        sim = Simulation(seed, stations=(name,), horizon=60.0, changes=1,
                         drop_probability=drop_probability)
        if len(sim.schedule()) == 1:
            sim.connect(app)
            when, station, price = sim.schedule()[0]
            return sim, station, price, when
    raise AssertionError('no seed with a single planned price change')


def test_send_decision_is_taken_at_every_trigger():
    seen = set()
    for seed in range(1, 9):
        sim = Simulation(seed, stations=(f'A{seed}', f'B{seed}', f'C{seed}'))
        sim.connect(app)
        _check_every_trigger(sim, seen)
    assert {'send', 'equal', 'in_flight'} <= seen, f'arrangements exercised: {seen}'


def test_lost_send_blocks_resend_until_it_is_abandoned():
    sim, station, price, when = _single_change_sim('lost', drop_probability=1.0)
    sim.run_until(when)
    sends = _sends_to(sim, station)
    assert [r.price for r in sends] == [price]
    sim.request_wake_up(when + 1.0)
    sim.run_until(when + 1.0)
    assert len(_sends_to(sim, station)) == 1, 'a due time must not resend the price in flight'
    sim.run_until(when + 31.0)
    sends = _sends_to(sim, station)
    assert len(sends) == 2, 'the abandoned send must be followed by one new send'
    assert all(r.price == price for r in sends)
    assert 30.0 <= sends[1].sent_at - when <= 31.0


def test_acknowledged_price_is_not_sent_again():
    sim, station, price, when = _single_change_sim('acked', drop_probability=0.0)
    sim.run_until(when)
    assert len(_sends_to(sim, station)) == 1
    while not sim.acks():
        assert sim.step(), 'the send was never acknowledged'
    assert sim.applied_price(station) == price
    assert len(_sends_to(sim, station)) == 1, 'the acknowledgement must not trigger a resend'
    later = sim.now + 1.0
    sim.request_wake_up(later)
    sim.run_until(later)
    assert len(_sends_to(sim, station)) == 1, 'a due time after the acknowledgement must not send'
