import app
from nrvv_env import Simulation

STATION = 'S0'
SEEDS = (1, 2, 3)
EARLIER = ['1.00', '2.00', '3.00', '4.00', '5.00', '6.00']
P1 = '10.00'
D = '12.50'
X = '11.00'
N = 7
STEP_LIMIT = 5000


def _simulation(seed):
    sim = Simulation(app, seed, stations=[STATION])
    sim.outages = {STATION: []}
    sim._script_by_tick = {}
    return sim


def _change(sim, *prices):
    sim._script_by_tick.setdefault(sim.tick + 1, []).extend((STATION, p) for p in prices)
    sim.step()


def _settle(sim):
    for _ in range(STEP_LIMIT):
        view = sim.server_state(STATION)
        if view['in_flight_seq'] is None and not view['pending']:
            return
        sim.step()
    raise AssertionError('not settled')


def _step_through_ack(sim, seq):
    for _ in range(STEP_LIMIT):
        arrivals = [a.arrived for a in sim.acks if a.seq == seq and a.arrived is not None]
        if arrivals and min(arrivals) <= sim.tick + 1:
            sim.step()
            return sim.tick
        sim.step()
    raise AssertionError('ack of seq %d never delivered' % seq)


def _reach_in_flight_p1(sim):
    for price in EARLIER:
        _change(sim, price)
        _settle(sim)
    _change(sim, P1)
    view = sim.server_state(STATION)
    assert view['in_flight_seq'] == N, view
    assert view['in_flight_price'] == P1, view


def test_ack_sends_pending_desired_price_when_it_differs():
    for seed in SEEDS:
        sim = _simulation(seed)
        _reach_in_flight_p1(sim)
        _change(sim, D)
        view = sim.server_state(STATION)
        assert view['pending'], (seed, view)
        assert view['desired_price'] == D, (seed, view)
        assert view['in_flight_seq'] == N and view['in_flight_price'] == P1, (seed, view)

        ack_tick = _step_through_ack(sim, N)

        view = sim.server_state(STATION)
        assert view['shown_price'] == P1, (seed, view)
        follow = [s for s in sim.sends if s.seq == N + 1]
        assert len(follow) == 1, (seed, follow)
        assert follow[0].price == D and follow[0].tick == ack_tick, (seed, follow)
        assert view['in_flight_seq'] == N + 1 and view['in_flight_price'] == D, (seed, view)


def test_ack_with_desired_equal_to_shown_sends_nothing_and_goes_idle():
    for seed in SEEDS:
        sim = _simulation(seed)
        _reach_in_flight_p1(sim)
        _change(sim, X, P1)
        view = sim.server_state(STATION)
        assert view['pending'], (seed, view)
        assert view['desired_price'] == P1, (seed, view)
        assert view['in_flight_seq'] == N and view['in_flight_price'] == P1, (seed, view)

        _step_through_ack(sim, N)

        view = sim.server_state(STATION)
        assert view['shown_price'] == P1, (seed, view)
        assert not view['pending'], (seed, view)
        assert view['in_flight_seq'] is None and view['in_flight_price'] is None, (seed, view)
        assert [s for s in sim.sends if s.seq > N] == [], seed

        for _ in range(sim.max_timeout + 10):
            sim.step()
        view = sim.server_state(STATION)
        assert view['in_flight_seq'] is None and not view['pending'], (seed, view)
        assert [s for s in sim.sends if s.seq > N] == [], seed
