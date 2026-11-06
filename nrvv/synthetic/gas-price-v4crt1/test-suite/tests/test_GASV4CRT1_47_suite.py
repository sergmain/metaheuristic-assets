import inspect

import app
from nrvv_env import Simulation

STATIONS = ('s1', 's2')
SEEDS = (1, 2, 3, 4, 5)
MAX_STEPS = 1000
SERVICE_METHODS = ('set_desired_price', 'inspect_station', 'receive_acknowledgement')
PORT_KEYWORDS = ('send_price_update', 'outbound', 'outbound_port', 'port', 'send', 'send_update')


def _sim(seed, **options):
    sim = Simulation(seed, STATIONS, changes=0, **options)
    return _build(sim)


def _build(sim):
    classes = [cls for _, cls in inspect.getmembers(app, inspect.isclass)
               if all(callable(getattr(cls, name, None)) for name in SERVICE_METHODS)]
    assert classes, 'app defines no class offering the service operations'
    cls = classes[0]
    port = sim.send_price_update
    attempts = [((port,), {})] + [((), {keyword: port}) for keyword in PORT_KEYWORDS]
    for args, keywords in attempts:
        try:
            service = cls(*args, **keywords)
        except TypeError:
            continue
        return sim.connect(service)
    raise AssertionError('cannot construct the service from the outbound port')


def test_no_update_sent_to_station_while_first_update_outstanding():
    for seed in SEEDS:
        sim = _sim(seed)
        sim.issue_desired_price('s1', 1)
        assert len(sim.sends) == 1
        assert sim.sends[0].station == 's1' and sim.sends[0].price == 1

        sim.issue_desired_price('s1', 2)
        sim.issue_desired_price('s1', 3)
        assert sim.outstanding('s1') == 1
        assert len(sim.sends) == 1, 'update sent while the first one is outstanding'

        for _ in range(MAX_STEPS):
            sends_before = len(sim.sends)
            sim.step()
            if sim.acks:
                break
            assert len(sim.sends) == sends_before, 'update sent while the first one is outstanding'
        else:
            raise AssertionError('first update was never acknowledged')

        ack_step = sim.acks[0].step
        sim.run()
        later = sim.sends[1:]
        assert later, 'no update sent after the in-flight slot was freed'
        assert all(s.step >= ack_step for s in later)


def test_next_update_sent_only_after_in_flight_slot_is_free():
    for seed in SEEDS:
        sim = _sim(seed)
        sim.issue_desired_price('s1', 1)
        sim.issue_desired_price('s1', 2)
        sim.issue_desired_price('s1', 3)
        sim.run()

        s1_sends = [s for s in sim.sends if s.station == 's1']
        assert len(s1_sends) == 2
        first, second = s1_sends
        ack = next(a for a in sim.acks if a.station == 's1')
        assert ack.price == 1
        assert first.outstanding_before == 0
        assert second.outstanding_before == 0
        assert ack.step <= second.step
        assert second.price == 3
        assert second.confirmed_at_send == 1


def test_no_send_while_station_has_update_in_flight_under_random_changes():
    total = 0
    for seed in range(25):
        sim = Simulation(seed, STATIONS, changes=40, horizon=40,
                         max_update_delay=6, max_ack_delay=6)
        _build(sim).run()
        for send in sim.sends:
            assert send.outstanding_before == 0, (
                f'seed {seed}: update to {send.station} sent with {send.outstanding_before} in flight')
        total += len(sim.sends)
    assert total > 0


def test_in_flight_slot_is_per_station():
    for seed in SEEDS:
        sim = _sim(seed)
        sim.issue_desired_price('s1', 1)
        sim.issue_desired_price('s1', 2)
        sim.issue_desired_price('s2', 4)
        assert [s.station for s in sim.sends] == ['s1', 's2']
        assert sim.outstanding('s1') == 1
        assert sim.outstanding('s2') == 1


def test_price_already_in_flight_is_not_resent():
    for seed in SEEDS:
        sim = _sim(seed)
        sim.issue_desired_price('s1', 1)
        sim.issue_desired_price('s1', 2)
        sim.issue_desired_price('s1', 1)
        sim.run()
        assert len(sim.sends) == 1
        assert sim.sends[0].price == 1
        assert all(s.outstanding_before == 0 for s in sim.sends)
