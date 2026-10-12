"""GASV4PRDA-35: one outstanding-update slot per station (GASV4PRDA-13)."""

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)


def _simulate(seed, **options):
    sim = Simulation(seed=seed, server=app, **options)
    sim.run_until_idle()
    return sim


def _quiet(**options):
    """No loss, duplicates or outages; every station gets a desired-price change each second."""
    settings = dict(loss_rate=0.0, duplicate_rate=0.0, outages=False, change_rate=1.0)
    settings.update(options)
    return settings


def _first_acks(sim, station_id):
    """Earliest time the server received an acknowledgement for each sequence number."""
    first = {}
    for ack in sim.ack_calls:
        if ack.station_id == station_id:
            first.setdefault(ack.sequence_number, ack.time)
    return first


def _fresh_sends(sim, station_id):
    """First send of each sequence number; every other send must repeat the outstanding update."""
    fresh = []
    seen = set()
    for call in sim.send_calls:
        if call.station_id != station_id:
            continue
        if fresh and call.sequence_number == fresh[-1].sequence_number:
            assert call.price == fresh[-1].price, 'resend changed the price of the outstanding update'
            continue
        assert call.sequence_number not in seen, 'an earlier update was sent again after a newer one'
        seen.add(call.sequence_number)
        fresh.append(call)
    return fresh


def _assert_one_outstanding(sim, station_id):
    """A fresh update needs an empty slot: the previous one acknowledged, and numbers count up by one."""
    acked = _first_acks(sim, station_id)
    fresh = _fresh_sends(sim, station_id)
    for previous, current in zip(fresh, fresh[1:]):
        assert current.sequence_number == previous.sequence_number + 1, 'sequence number did not increase by one'
        assert previous.sequence_number in acked, 'fresh update sent while the previous one was unacknowledged'
        assert acked[previous.sequence_number] <= current.time, 'fresh update sent before the acknowledgement arrived'
    return fresh


def _assert_sent_on_empty_slot(sim, station_id):
    """A desired-price change arriving with an empty slot and a new price must be sent as a fresh update."""
    acked = _first_acks(sim, station_id)
    fresh = _fresh_sends(sim, station_id)
    for change in sim.central.changes:
        if change.station_id != station_id:
            continue
        t = change.time
        earlier = [f for f in fresh if f.time < t]
        last = earlier[-1] if earlier else None
        slot_empty = last is None or (
            last.sequence_number in acked and acked[last.sequence_number] < t
        )
        last_price = last.price if last else None
        if slot_empty and change.price != last_price:
            sent_now = [f for f in fresh if f.time == t]
            assert sent_now, 'update was not accepted although the slot was empty'
            assert sent_now[0].price == change.price


def test_slot_accepts_one_update_and_rejects_the_next_until_acknowledged():
    for seed in SEEDS:
        sim = _simulate(seed, **_quiet(stations=['S1']))
        fresh = _assert_one_outstanding(sim, 'S1')
        _assert_sent_on_empty_slot(sim, 'S1')
        assert len(fresh) >= 3
        assert len(sim.send_calls) < len(sim.central.changes), 'no change was rejected while the slot was full'


def test_each_station_sends_next_update_only_after_matching_ack():
    for seed in SEEDS:
        sim = _simulate(seed, **_quiet(stations=3))
        for station_id in ('S1', 'S2', 'S3'):
            fresh = _assert_one_outstanding(sim, station_id)
            _assert_sent_on_empty_slot(sim, station_id)
            assert len(fresh) >= 2


def test_slot_rule_holds_with_loss_duplicates_and_outages():
    for seed in SEEDS:
        sim = _simulate(seed, stations=3, change_rate=1.0)
        for station_id, station in sim.stations.items():
            _assert_one_outstanding(sim, station_id)
            _assert_sent_on_empty_slot(sim, station_id)
            for when, sequence_number, price in station.received:
                assert any(
                    call.station_id == station_id
                    and call.sequence_number == sequence_number
                    and call.price == price
                    for call in sim.send_calls
                ), 'station received an update that was never sent with that number and price'


def test_sequence_numbers_are_counted_per_station():
    for seed in SEEDS:
        sim = _simulate(seed, **_quiet(stations=3))
        numbers = {}
        for station_id in ('S1', 'S2', 'S3'):
            fresh = _assert_one_outstanding(sim, station_id)
            assert len(fresh) >= 2
            numbers[station_id] = {call.sequence_number for call in fresh}
        shared = (numbers['S1'] & numbers['S2']) | (numbers['S1'] & numbers['S3']) | (numbers['S2'] & numbers['S3'])
        assert shared, 'stations share no sequence number, so the numbers are not counted per station'
