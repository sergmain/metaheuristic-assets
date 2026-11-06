'''GASV4ACCJ-7: do not resend a price the station already holds or is receiving.

The server is the module app; the environment is nrvv_env.Simulation. Scheduled
desired-price changes are injected through Simulation._push.
'''
import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)
STATION = 'S1'
FIRST = 100
OTHER = 120
SETTLE_SECONDS = 120  # longer than the 60 s slot rule, so server-side sends fire
CHANGE = 'change'  # kind of a scheduled desired-price change inside nrvv_env


def _simulation(seed):
    # horizon=0 schedules no random changes; loss_rate=0 and no unreachable
    # intervals let every send be delivered and acknowledged.
    sim = Simulation(seed, app, station_ids=(STATION,), horizon=0, loss_rate=0.0)
    sim.stations[STATION].unreachable = []
    return sim


def _change_at(sim, when, price):
    sim._push(when, CHANGE, (STATION, price))


def _settle(sim):
    sim.advance_to(sim.now + SETTLE_SECONDS)
    sim.run_until_idle()


def _sends(sim, price=None, since=0):
    return [s for s in sim.sends
            if s.station_id == STATION and s.sent_at >= since
            and (price is None or s.price == price)]


def test_no_send_when_station_already_acknowledged_price():
    for seed in SEEDS:
        sim = _simulation(seed)
        _change_at(sim, 1, FIRST)
        _settle(sim)
        assert sim.applied_price(STATION) == FIRST, 'precondition: station acknowledged FIRST (seed %d)' % seed
        since = sim.now + 1
        _change_at(sim, since, FIRST)
        _settle(sim)
        assert _sends(sim, since=since) == [], 'seed %d' % seed


def test_no_additional_send_while_same_price_is_in_flight():
    for seed in SEEDS:
        sim = _simulation(seed)
        # Both changes fall in the same second, before any delivery or
        # acknowledgement of the first send can be processed.
        _change_at(sim, 1, FIRST)
        _change_at(sim, 1, FIRST)
        _settle(sim)
        assert len(_sends(sim, FIRST)) == 1, 'seed %d' % seed


def test_price_is_sent_when_station_neither_holds_nor_awaits_it():
    for seed in SEEDS:
        sim = _simulation(seed)
        _change_at(sim, 1, OTHER)
        _settle(sim)
        assert sim.applied_price(STATION) == OTHER, 'precondition: station holds OTHER (seed %d)' % seed
        since = sim.now + 1
        _change_at(sim, since, FIRST)
        _settle(sim)
        assert _sends(sim, FIRST, since=since), 'seed %d' % seed
        assert sim.applied_price(STATION) == FIRST, 'seed %d' % seed


def test_price_is_sent_when_only_a_different_price_is_in_flight():
    for seed in SEEDS:
        sim = _simulation(seed)
        _change_at(sim, 1, OTHER)
        _change_at(sim, 1, FIRST)
        _settle(sim)
        assert _sends(sim, FIRST), 'seed %d' % seed
