'''GASV4RDF1-54: notify the pricing team within one minute of the acknowledgement showing that a station holds the latest desired price.

The simulation has no clock, so the one-minute window is measured in logical steps. The receipt of an acknowledgement is the step in which app.receive_acknowledgement is called. The app can only act inside a call, so a notice issued for that receipt must be recorded in the same step (arrival == ack.step). Any notice recorded in a later step is outside the window.
'''

import app
from nrvv_env import Simulation


def _desired_at(sim, station, step):
    desired = None
    for call in sim.call_log:
        if call.station == station and call.step < step:
            desired = call.price
    return desired


def _confirming_acks(sim):
    return [ack for ack in sim.ack_log
            if ack.price == _desired_at(sim, ack.station, ack.step)]


def _first_confirmations(sim):
    seen = set()
    out = []
    for ack in _confirming_acks(sim):
        key = (ack.station, ack.price)
        if key not in seen:
            seen.add(key)
            out.append(ack)
    return out


def _notices_at(sim, ack):
    return [n for n in sim.notices
            if n.arrival == ack.step and n.station == ack.station and n.price == ack.price]


def test_notice_issued_at_receipt_of_latest_price_ack():
    confirmed = 0
    for seed in range(20):
        sim = Simulation(app, seed, calls=12)
        sim.run()
        assert sim.is_quiet(), 'seed %d: simulation did not finish' % seed
        for ack in _first_confirmations(sim):
            confirmed += 1
            assert _notices_at(sim, ack), (
                'seed %d: no pricing notice for %s=%s in the step of its acknowledgement (step %d); notices: %r'
                % (seed, ack.station, ack.price, ack.step, sim.notices))
    assert confirmed > 0, 'no acknowledgement showed a latest desired price in any run'


def test_notice_names_station_and_confirmed_price():
    checked = 0
    for seed in range(20):
        sim = Simulation(app, seed, calls=12)
        sim.run()
        confirming = {(a.step, a.station, a.price) for a in _confirming_acks(sim)}
        for n in sim.notices:
            checked += 1
            assert (n.arrival, n.station, n.price) in confirming, (
                'seed %d: notice %r does not match a confirming acknowledgement' % (seed, n))
    assert checked > 0, 'no pricing notice was issued in any run'


def test_latest_price_notified_when_desired_price_changes_while_updates_outstanding():
    script = [('S1', 10), ('S1', 20), ('S1', 30), ('S2', 5), ('S2', 6)]
    final = {'S1': 30, 'S2': 6}
    for seed in range(15):
        sim = Simulation(app, seed, script=script)
        sim.run()
        assert sim.is_quiet(), 'seed %d: simulation did not finish' % seed
        for station, price in final.items():
            acks = [a for a in sim.ack_log if a.station == station and a.price == price]
            assert acks, 'seed %d: %s never acknowledged its latest price %s' % (seed, station, price)
            assert _notices_at(sim, acks[0]), (
                'seed %d: no pricing notice for %s=%s in the step of its acknowledgement (step %d)'
                % (seed, station, price, acks[0].step))


def test_every_first_confirmation_notified_with_repeated_prices():
    confirmed = 0
    for seed in range(30):
        sim = Simulation(app, seed, stations=('S1', 'S2', 'S3'), calls=25, prices=(1, 3))
        sim.run()
        assert sim.is_quiet(), 'seed %d: simulation did not finish' % seed
        for ack in _first_confirmations(sim):
            confirmed += 1
            assert _notices_at(sim, ack), (
                'seed %d: no pricing notice for %s=%s in the step of its acknowledgement (step %d)'
                % (seed, ack.station, ack.price, ack.step))
    assert confirmed > 0, 'no acknowledgement showed a latest desired price in any run'
