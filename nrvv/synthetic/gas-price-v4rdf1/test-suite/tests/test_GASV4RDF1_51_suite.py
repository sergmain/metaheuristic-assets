import app
from nrvv_env import Simulation


def _normalise(state):
    if hasattr(state, '_asdict'):
        fields = {k.lower(): v for k, v in state._asdict().items()}
    elif isinstance(state, dict):
        fields = {str(k).lower(): v for k, v in state.items()}
    elif hasattr(state, '__dict__'):
        fields = {k.lower(): v for k, v in vars(state).items()}
    else:
        return tuple(state)

    def pick(word):
        for key, value in fields.items():
            if word in key:
                return value
        raise AssertionError('no %s field in %r' % (word, state))

    outstanding = pick('outstanding')
    if isinstance(outstanding, (list, tuple)):
        outstanding = len(outstanding)
    return pick('confirm'), pick('desire'), outstanding


def test_superseded_price_not_resent_and_ack_matches_superseded_entry():
    station = 'S51'
    sim = Simulation(app, seed=51, stations=(station,), script=[(station, 'P1'), (station, 'P2')])

    sim._issue_call()  # desired P1
    assert [s.price for s in sim.sent_log] == ['P1']
    sim._deliver_update()  # station receives P1; its acknowledgement is pending
    assert sim.pending_acks(station) == 1

    mark = len(sim.sent_log)
    sim._issue_call()  # desired P2 before any acknowledgement arrives
    while sim.in_flight():
        sim._deliver_update()
    later = [s.price for s in sim.sent_log[mark:]]
    assert later.count('P2') == 1
    assert 'P1' not in later

    sim._deliver_ack()  # first outstanding update acknowledged
    assert sim.last_ack_price(station) == 'P1'
    confirmed, desired, outstanding = _normalise(sim.query(station))
    assert confirmed == 'P1'
    assert desired == 'P2'
    assert outstanding == 1

    sim.run()
    confirmed, desired, outstanding = _normalise(sim.query(station))
    assert confirmed == 'P2'
    assert outstanding == 0
    all_prices = [s.price for s in sim.sent_log]
    assert all_prices.count('P2') == 1
    assert all_prices.count('P1') == 1


def test_only_current_desired_price_is_ever_sent_under_random_calls():
    for seed in (5101, 5102, 5103):
        names = ('A%d' % seed, 'B%d' % seed)
        sim = Simulation(app, seed, stations=names, calls=40, prices=(1, 4))
        sim.run()
        assert sim.sent_log
        for sent in sim.sent_log:
            assert sent.price == sent.desired, sent
