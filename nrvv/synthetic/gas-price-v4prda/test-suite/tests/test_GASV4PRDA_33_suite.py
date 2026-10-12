# GASV4PRDA-33: after overwrites, the update built at send time carries only the latest desired price (GASV4PRDA-12).
from nrvv_env import Simulation

import app

STATION = 'S1'
OTHER = 'S2'
WARM_UP = 50
SEEDS = (1, 2, 3, 4, 5)


def _simulation(seed):
    # No random central changes, no loss, no duplicates, no outages: the only
    # traffic is the scripted changes, so every send and acknowledgement is predictable.
    return Simulation(
        seed,
        server=app,
        stations=[STATION, OTHER],
        change_rate=0.0,
        loss_rate=0.0,
        duplicate_rate=0.0,
        outages=False,
        horizon=60,
    )


def _overwrite_while_slot_full(seed, prices, other_price=None):
    # nrvv_env offers no public way to submit a scripted change, so the change is
    # made on the server object that the simulation bound to its send port.
    sim = _simulation(seed)
    server = sim._server
    # The warm-up change is sent at once and stays unacknowledged, so the slot is full.
    server.desired_price_change(STATION, WARM_UP)
    sent_before = len(sim.send_calls)
    for price in prices:
        server.desired_price_change(STATION, price)
    assert len(sim.send_calls) == sent_before, 'seed %d: a change sent while the slot was full' % seed
    if other_price is not None:
        server.desired_price_change(OTHER, other_price)
    sim.run_until_idle()
    return sim, sent_before


def _station_prices_after(sim, sent_before):
    return [c.price for c in sim.send_calls[sent_before:] if c.station_id == STATION]


def _station_prices_ever_sent(sim):
    return [c.price for c in sim.send_calls if c.station_id == STATION]


def test_update_sent_at_send_time_carries_second_value_not_first():
    for seed in SEEDS:
        sim, sent_before = _overwrite_while_slot_full(seed, prices=(10, 20))
        after = _station_prices_after(sim, sent_before)
        assert after, 'seed %d: no update was sent once the slot emptied' % seed
        assert set(after) == {20}, 'seed %d: update carried %r' % (seed, after)
        assert 10 not in _station_prices_ever_sent(sim), 'seed %d: first value was sent' % seed
        received = [p for _, _, p in sim.stations[STATION].received]
        assert 10 not in received, 'seed %d: station received first value' % seed
        assert sim.stations[STATION].display == 20


def test_third_overwrite_send_reflects_only_most_recent_value():
    for seed in SEEDS:
        sim, sent_before = _overwrite_while_slot_full(seed, prices=(10, 20, 30))
        after = _station_prices_after(sim, sent_before)
        assert after, 'seed %d: no update was sent once the slot emptied' % seed
        assert set(after) == {30}, 'seed %d: update carried %r' % (seed, after)
        ever = _station_prices_ever_sent(sim)
        assert 10 not in ever and 20 not in ever, 'seed %d: overwritten value was sent' % seed
        assert sim.stations[STATION].display == 30


def test_other_station_change_leaves_first_station_update_unchanged():
    for seed in SEEDS:
        sim, sent_before = _overwrite_while_slot_full(seed, prices=(10, 20), other_price=40)
        after = _station_prices_after(sim, sent_before)
        assert after, 'seed %d: no update was sent once the slot emptied' % seed
        assert set(after) == {20}, 'seed %d: update carried %r' % (seed, after)
        assert 40 not in _station_prices_ever_sent(sim), 'seed %d: other station price leaked' % seed
        other_sent = [c.price for c in sim.send_calls if c.station_id == OTHER]
        assert other_sent == [40], 'seed %d: other station sends %r' % (seed, other_sent)
        assert sim.stations[STATION].display == 20
