# GASV4ELMB-3: a price update is sent to the station on every desired-price change.
import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)


def _new_sim(seed, stations):
    sim = Simulation(app, seed, stations=list(stations), active_ticks=5)
    sim._script_by_tick = {}
    sim.outages = {s: [] for s in stations}
    return sim


def _change_at_next_step(sim, station, price):
    tick = sim.tick + 1
    sim._script_by_tick.setdefault(tick, []).append((station, price))
    sim.step()
    return tick


def _settle(sim, station, limit=500):
    for _ in range(limit):
        if not sim.in_flight() and sim.server_state(station)['in_flight_seq'] is None:
            return
        sim.step()
    raise AssertionError('server did not settle after %d ticks (seed %r)' % (limit, sim.seed))


def _assert_single_update(sim, station, start, end, price):
    window = [s for s in sim.sends if s.tick >= start and (end is None or s.tick < end)]
    assert window, 'no update sent after the change'
    assert all(s.station == station for s in window), 'update addressed to another station'
    assert len([s for s in window if not s.retransmission]) == 1, 'not exactly one update'
    assert all(s.price == price for s in window), 'update carries the old price'


def test_each_desired_price_change_sends_one_update_to_station_with_new_price():
    for seed in SEEDS:
        station = 'G%d' % seed
        p1, p2, p3 = seed, seed + 5, seed + 11
        sim = _new_sim(seed, [station])
        _change_at_next_step(sim, station, p1)
        _settle(sim, station)
        assert sim.server_state(station)['desired_price'] == p1

        t2 = _change_at_next_step(sim, station, p2)
        assert sim.server_state(station)['desired_price'] == p2
        _settle(sim, station)

        t3 = _change_at_next_step(sim, station, p3)
        assert sim.server_state(station)['desired_price'] == p3
        _settle(sim, station)

        _assert_single_update(sim, station, t2, t3, p2)
        _assert_single_update(sim, station, t3, None, p3)


def test_change_sends_update_only_to_changed_station():
    for seed in SEEDS:
        changed, other = 'H%d-A' % seed, 'H%d-B' % seed
        sim = _new_sim(seed, [changed, other])
        _change_at_next_step(sim, changed, seed)
        _settle(sim, changed)
        t = _change_at_next_step(sim, changed, seed + 7)
        _settle(sim, changed)
        assert sim.server_state(changed)['desired_price'] == seed + 7
        _assert_single_update(sim, changed, t, None, seed + 7)
        assert not [s for s in sim.sends if s.station == other], 'update sent to unchanged station'
