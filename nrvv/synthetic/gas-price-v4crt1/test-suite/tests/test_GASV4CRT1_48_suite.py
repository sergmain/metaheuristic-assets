import inspect

import app
from nrvv_env import Simulation


def _build_service(sim):
    # The service class is the one CapWords class of app offering the Interface
    # operations; it takes the outbound port (sim.send_price_update) as its argument.
    candidates = [obj for name, obj in vars(app).items()
                  if inspect.isclass(obj) and name[:1].isupper()
                  and callable(getattr(obj, 'set_desired_price', None))]
    assert len(candidates) == 1, 'app must provide exactly one service class'
    service = candidates[0](sim.send_price_update)
    sim.connect(service)
    return service


def _sends_for(sim, station):
    return [s for s in sim.sends if s.station == station]


def test_second_update_held_while_first_unacknowledged():
    # The second desired price arrives while the first update is still in flight.
    for seed in range(5):
        sim = Simulation(seed, ['S1'], changes=0)
        _build_service(sim)

        sim.issue_desired_price('S1', 1)
        sim.step()  # the first update is delivered or still in transit; no ack yet
        assert sim.outstanding('S1') == 1

        sim.issue_desired_price('S1', 2)
        assert len(_sends_for(sim, 'S1')) == 1
        assert sim.sends[0].price == 1
        assert sim.outstanding('S1') == 1

        sim.run()
        sends = _sends_for(sim, 'S1')
        assert len(sends) == 2
        assert sends[1].price == 2
        assert sends[1].outstanding_before == 0
        assert sim.acks[0].price == 1
        assert sends[1].step >= sim.acks[0].step


def test_second_update_sent_only_after_first_is_acknowledged():
    # Ordering check: the second update's send step never precedes the ack of the first.
    for seed in range(5):
        sim = Simulation(seed, ['S1'], changes=0)
        _build_service(sim)

        sim.issue_desired_price('S1', 1)
        sim.issue_desired_price('S1', 3)  # back to back, before any step
        sim.run()

        sends = _sends_for(sim, 'S1')
        first_ack_steps = [a.step for a in sim.acks if a.station == 'S1']
        assert len(sends) == 2
        assert sends[0].price == 1
        assert sends[1].price == 3
        assert sends[1].step >= first_ack_steps[0]
        assert sim.displayed('S1') == 3


def test_no_two_updates_unacknowledged_at_same_station():
    # Random desired-price changes over two stations: no send while another is outstanding.
    for seed in range(8):
        sim = Simulation(seed, ['A', 'B'], changes=30, horizon=20)
        _build_service(sim)
        sim.run()

        assert sim.sends
        for send in sim.sends:
            assert send.outstanding_before == 0, (seed, send)
        assert sim.outstanding('A') == 0
        assert sim.outstanding('B') == 0


def test_each_send_follows_an_acknowledgement_of_the_previous_one():
    # For every station, the k-th send (k >= 2) happens after the (k-1)-th acknowledgement.
    for seed in range(8):
        sim = Simulation(seed, ['A', 'B'], changes=30, horizon=20)
        _build_service(sim)
        sim.run()

        for station in ('A', 'B'):
            sends = _sends_for(sim, station)
            acks = [a for a in sim.acks if a.station == station]
            for k in range(1, len(sends)):
                acked_before = sum(1 for a in acks if a.step <= sends[k].step)
                assert acked_before >= k, (seed, station, k)


def test_displayed_price_ends_at_latest_desired_price():
    # Serialised updates still converge: the station ends on the newest desired price.
    for seed in range(8):
        sim = Simulation(seed, ['A', 'B'], changes=25, horizon=20)
        _build_service(sim)
        sim.run()

        for station in ('A', 'B'):
            if sim.desired(station) is not None:
                assert sim.displayed(station) == sim.desired(station), (seed, station)
