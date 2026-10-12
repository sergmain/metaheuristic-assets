import importlib

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)


def _run(seed, *, stations, change_rate, prices=(10, 20, 30, 40, 50), horizon=120):
    importlib.reload(app)
    sim = Simulation(
        seed=seed,
        server=app,
        stations=stations,
        prices=prices,
        horizon=horizon,
        change_rate=change_rate,
        loss_rate=0.0,
        duplicate_rate=0.0,
        outages=False,
    )
    sim.run_until_idle()
    return sim


def _outstanding_at(sim, station_id, t):
    '''The last update sent to the station before second t, if no acknowledgement of it arrived by t.'''
    sent = [c for c in sim.send_calls if c.station_id == station_id and c.time < t]
    if not sent:
        return None
    last = sent[-1]
    for ack in sim.ack_calls:
        if ack.station_id == station_id and ack.sequence_number == last.sequence_number and ack.time <= t:
            return None
    return last


def _held_changes(sim):
    '''Every desired-price change that arrived while its station's slot was full.'''
    held = []
    for change in sim.central.changes:
        outstanding = _outstanding_at(sim, change.station_id, change.time)
        if outstanding is not None:
            held.append((change, outstanding))
    return held


def _check_held_prices(seeds, *, stations, change_rate, prices=(10, 20, 30, 40, 50)):
    checked = 0
    for seed in seeds:
        sim = _run(seed, stations=stations, change_rate=change_rate, prices=prices)
        for change, outstanding in _held_changes(sim):
            sid = change.station_id
            acks = [
                a for a in sim.ack_calls
                if a.station_id == sid and a.sequence_number == outstanding.sequence_number and a.time > change.time
            ]
            assert acks, (seed, change, outstanding)
            ack_time = acks[0].time
            expected = sim.central.desired_at(sid, ack_time)
            sent = [c for c in sim.send_calls if c.station_id == sid and c.time == ack_time]
            if expected == outstanding.price:
                assert sent == [], (seed, change, outstanding, sent)
            else:
                assert len(sent) == 1, (seed, change, outstanding, sent)
                assert sent[0].price == expected, (seed, change, outstanding, sent)
                assert sent[0].sequence_number != outstanding.sequence_number
            checked += 1
    return checked


def test_newer_change_while_slot_full_emits_nothing():
    held = 0
    for seed in SEEDS:
        sim = _run(seed, stations=3, change_rate=0.3)
        for change, outstanding in _held_changes(sim):
            held += 1
            sent = [c for c in sim.send_calls if c.station_id == change.station_id and c.time == change.time]
            assert sent == [], (seed, change, outstanding, sent)
    assert held > 0


def test_held_price_sent_once_when_matching_ack_arrives():
    assert _check_held_prices(SEEDS, stations=3, change_rate=0.3) > 0


def test_held_price_equal_to_sent_price_is_not_resent():
    assert _check_held_prices(SEEDS, stations=2, change_rate=0.5, prices=(10, 20)) > 0


def test_every_second_change_held_while_slot_full():
    assert _check_held_prices(SEEDS, stations=1, change_rate=1.0) > 0
