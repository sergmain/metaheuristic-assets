from nrvv_env import Simulation

import app

STATION = 'S1'
SEEDS = (1, 2, 3)


def _make(seed, script):
    return Simulation(app, seed, stations=(STATION,), script=script)


def _drain(sim):
    while sim.in_flight() or sim.pending_acks():
        if sim.in_flight():
            sim._deliver_update()
        else:
            sim._deliver_ack()


def _deliver_price(sim, price):
    i = next(i for i, (_, p) in enumerate(sim._in_flight) if p == price)
    station, p = sim._in_flight.pop(i)
    sim.stations[station].receive(p)


def _settled_at_100(seed):
    sim = _make(seed, [(STATION, 100), (STATION, 105), (STATION, 110), (STATION, 105)])
    sim._issue_call()
    _drain(sim)
    confirmed, desired, outstanding = sim.query(STATION)
    assert (confirmed, desired, outstanding) == (100, 100, 0)
    return sim


def test_desired_change_to_105_sends_one_update_and_appends_it():
    for seed in SEEDS:
        sim = _settled_at_100(seed)
        mark = len(sim.sent_log)
        sim._issue_call()
        assert [u.price for u in sim.sent_log[mark:]] == [105]
        assert sim.in_flight() == [(STATION, 105)]
        assert sim.query(STATION)[2] == 1


def test_desired_change_to_110_while_105_outstanding_sends_110_and_appends_it():
    for seed in SEEDS:
        sim = _settled_at_100(seed)
        sim._issue_call()  # desired 105
        mark = len(sim.sent_log)
        sim._issue_call()  # desired 110
        assert [u.price for u in sim.sent_log[mark:]] == [110]
        assert sim.in_flight() == [(STATION, 105), (STATION, 110)]
        assert sim.query(STATION)[2] == 2


def test_desired_change_to_105_while_105_outstanding_sends_nothing():
    for seed in SEEDS:
        sim = _settled_at_100(seed)
        sim._issue_call()  # desired 105, outstanding [105]
        sim._issue_call()  # desired 110, outstanding [105, 110]
        mark = len(sim.sent_log)
        before = sim.in_flight()
        sim._issue_call()  # desired 105 again, outstanding already carries 105
        assert sim.sent_log[mark:] == []
        assert sim.in_flight() == before
        assert sim.query(STATION)[2] == 2


def test_ack_with_confirmed_differing_from_desired_sends_desired_price_once():
    for seed in SEEDS:
        sim = _settled_at_100(seed)
        sim._issue_call()  # desired 105
        sim._issue_call()  # desired 110
        sim._issue_call()  # desired 105, outstanding [105, 110]
        # acknowledge 105: confirmed becomes 105, equal to desired
        _deliver_price(sim, 105)
        sim._deliver_ack()
        assert sim.query(STATION)[2] == 1
        # acknowledge 110: confirmed 110 differs from desired 105, and no
        # outstanding update carries 105 any more
        _deliver_price(sim, 110)
        mark = len(sim.sent_log)
        sim._deliver_ack()
        assert [u.price for u in sim.sent_log[mark:]] == [105]
        assert sim.query(STATION)[2] == 1
        assert sim.in_flight() == [(STATION, 105)]


def test_every_sent_update_carries_the_desired_price_at_send_time():
    for seed in (11, 12, 13, 14):
        sim = Simulation(app, seed, stations=('S1', 'S2'), calls=30)
        sim.run()
        assert sim.sent_log
        for update in sim.sent_log:
            assert update.price == update.desired
