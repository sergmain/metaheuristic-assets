import app
from nrvv_env import Simulation

STATION = 'S1'
SEEDS = range(20)
P1, Q, P2, P3 = 1, 2, 3, 4  # confirmed, in-flight, desired during flight, latest desired


def _new_service(port):
    for name in ('PriceService', 'Service', 'PricingService', 'StationPriceService'):
        cls = getattr(app, name, None)
        if cls is not None:
            return cls(port)
    raise AttributeError('app defines no service class taking the outbound port')


def _simulation(seed, stations=(STATION,), changes=0, **kwargs):
    sim = Simulation(seed, list(stations), changes=changes, **kwargs)
    return sim.connect(_new_service(sim.send_price_update))


def _step_until(sim, predicate, limit=10000):
    for _ in range(limit):
        if predicate():
            return
        sim.step()
    raise AssertionError('condition not reached within limit')


def _last_desire_before(sim, station, step):
    price = None
    for d in sim.desires:
        if d.station == station and d.step <= step:
            price = d.price
    return price


def _run_flight_scenario(seed):
    # confirmed P1; Q in flight; desired P2 set during Q's flight; P3 set during P2's flight
    sim = _simulation(seed, max_update_delay=4, max_ack_delay=4)
    sim.issue_desired_price(STATION, P1)
    _step_until(sim, lambda: len(sim.acks) == 1)
    assert sim.outstanding(STATION) == 0
    sim.issue_desired_price(STATION, Q)
    assert sim.outstanding(STATION) == 1
    sim.issue_desired_price(STATION, P2)
    assert [s.price for s in sim.sends] == [P1, Q]
    _step_until(sim, lambda: len(sim.acks) == 2)
    assert [s.price for s in sim.sends] == [P1, Q, P2]
    assert sim.outstanding(STATION) == 1
    sim.issue_desired_price(STATION, P3)
    assert [s.price for s in sim.sends] == [P1, Q, P2]
    _step_until(sim, lambda: len(sim.acks) == 3)
    sim.run()
    return sim


def test_pending_change_sent_once_when_in_flight_ack_clears():
    for seed in SEEDS:
        sim = _run_flight_scenario(seed)
        sent = [s for s in sim.sends if s.price == P2]
        assert len(sent) == 1
        assert sent[0].step == sim.acks[1].step
        assert sent[0].confirmed_at_send == Q
        assert sent[0].desired_at_send == P2
        assert sent[0].outstanding_before == 0


def test_change_during_flight_sends_latest_desire_not_superseded_one():
    for seed in SEEDS:
        sim = _run_flight_scenario(seed)
        assert [s.price for s in sim.sends] == [P1, Q, P2, P3]
        assert sim.sends[3].step == sim.acks[2].step
        assert sim.sends[3].desired_at_send == P3
        assert sim.sends[3].confirmed_at_send == P2


def test_after_all_acks_display_shows_latest_desired_price():
    for seed in SEEDS:
        sim = _run_flight_scenario(seed)
        assert sim.displayed(STATION) == P3
        assert sim.desired(STATION) == P3
        assert sim.outstanding(STATION) == 0


def test_ack_with_desire_equal_to_confirmed_sends_nothing():
    for seed in SEEDS:
        sim = _simulation(seed, max_update_delay=4, max_ack_delay=4)
        sim.issue_desired_price(STATION, P1)
        _step_until(sim, lambda: len(sim.acks) == 1)
        sim.issue_desired_price(STATION, Q)
        sim.issue_desired_price(STATION, P2)
        sim.issue_desired_price(STATION, Q)  # back to the price about to be confirmed
        _step_until(sim, lambda: len(sim.acks) == 2)
        ack_step = sim.acks[1].step
        assert not [s for s in sim.sends if s.step == ack_step]
        sim.run()
        assert [s.price for s in sim.sends] == [P1, Q]
        assert sim.displayed(STATION) == Q


def test_each_ack_sends_latest_desire_only_when_it_differs_from_confirmed():
    for seed in SEEDS:
        sim = _simulation(seed, stations=('A', 'B', 'C'), changes=20)
        sim.run()
        for ack in sim.acks:
            desired = _last_desire_before(sim, ack.station, ack.step)
            here = [s for s in sim.sends if s.station == ack.station and s.step == ack.step]
            if desired == ack.price:
                assert here == []
            else:
                assert len(here) == 1
                assert here[0].price == desired


def test_no_update_sent_without_pending_change_or_with_update_in_flight():
    for seed in SEEDS:
        sim = _simulation(seed, stations=('A', 'B', 'C'), changes=20)
        sim.run()
        for s in sim.sends:
            assert s.outstanding_before == 0
            assert s.price == s.desired_at_send
            assert s.price != s.confirmed_at_send


def test_after_every_ack_displayed_price_converges_to_latest_desired():
    for seed in SEEDS:
        sim = _simulation(seed, stations=('A', 'B', 'C'), changes=20)
        sim.run()
        assert len(sim.acks) == len(sim.sends)
        for station in ('A', 'B', 'C'):
            assert sim.outstanding(station) == 0
            if sim.desired(station) is not None:
                assert sim.displayed(station) == sim.desired(station)
