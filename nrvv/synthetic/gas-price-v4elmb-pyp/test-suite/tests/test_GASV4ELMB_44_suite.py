# GASV4ELMB-44: a candidate equal to the shown price is not sent, and reverting to the shown price is suppressed.
import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)
STEP_LIMIT = 2000


def _quiet_sim(seed, base, name):
    sim = Simulation(app, seed, stations=[name])
    sim.tick = base
    sim._script_by_tick = {}
    sim.outages = {name: []}
    return sim


def _establish_shown(sim, name, price):
    sim._central_change(sim.tick, name, price)
    for _ in range(STEP_LIMIT):
        view = sim.server_state(name)
        if view['shown_price'] == price and view['in_flight_seq'] is None:
            return
        sim.step()
    raise AssertionError('seed %r: price %r never acknowledged' % (sim.seed, price))


def test_equal_candidate_is_not_sent_and_station_goes_idle():
    for seed in SEEDS:
        name = 'E%d' % seed
        sim = _quiet_sim(seed, 1000000 + seed * 10000, name)
        price = 4 + seed
        _establish_shown(sim, name, price)
        sim._central_change(sim.tick, name, price + 1)
        sim._central_change(sim.tick, name, price)
        mark = len(sim.sends)
        sim.step()
        assert sim.sends[mark:] == [], 'seed %r: update sent although candidate equals shown price' % seed
        view = sim.server_state(name)
        assert view['desired_price'] == price, 'seed %r: desired price wrong' % seed
        assert not view['pending'], 'seed %r: pending change not cleared' % seed
        assert view['in_flight_seq'] is None, 'seed %r: station not idle' % seed
        assert view['shown_price'] == price, 'seed %r: shown price changed' % seed


def test_changed_candidate_is_sent_and_revert_to_shown_price_is_suppressed():
    for seed in SEEDS:
        name = 'R%d' % seed
        sim = _quiet_sim(seed, 5000000 + seed * 10000, name)
        price = 4 + seed
        _establish_shown(sim, name, price)
        changed = price + 1
        mark = len(sim.sends)
        sim._central_change(sim.tick, name, changed)
        sim.step()
        sent = [s for s in sim.sends[mark:] if s.station == name and s.price == changed]
        assert sent, 'seed %r: no update carrying the changed price was sent' % seed
        assert not sent[0].retransmission, 'seed %r: first update reused a sequence number' % seed
        view = sim.server_state(name)
        assert view['in_flight_seq'] is not None, 'seed %r: update not in flight' % seed
        assert view['in_flight_price'] == changed, 'seed %r: in-flight price wrong' % seed
        assert view['shown_price'] == price, 'seed %r: shown price changed before acknowledgement' % seed
        mark = len(sim.sends)
        sim._central_change(sim.tick, name, price)
        sim.step()
        window = sim.sends[mark:]
        assert not [s for s in window if s.price == price], 'seed %r: shown price was sent again' % seed
        assert not [s for s in window if not s.retransmission], 'seed %r: new update sent for reverted price' % seed
        view = sim.server_state(name)
        assert view['shown_price'] == price, 'seed %r: shown price changed' % seed
