import inspect

import app
from nrvv_env import Simulation, STATIONS

SEEDS = (1, 2, 3, 4, 5, 6)


def _make_server(send_price_update):
    required = ('set_desired_price', 'acknowledgement_received', 'observe_station')
    for name in dir(app):
        obj = getattr(app, name)
        if name[:1].isupper() and inspect.isclass(obj) and all(hasattr(obj, m) for m in required):
            return obj(send_price_update)
    raise AssertionError('app has no server class providing the Interface operations')


def _run(seed):
    sim = Simulation(seed, _make_server)
    sim.run_until_idle()
    return sim


def _sends_to(sim, station):
    return [s for s in sim.sends if s.station == station]


def _acks_from(sim, station):
    return [a for a in sim.from_station if a.station == station]


def test_no_update_sent_while_previous_update_unacknowledged():
    for seed in SEEDS:
        sim = _run(seed)
        assert sim.sends, f'seed {seed}: no update was sent'
        for s in sim.sends:
            assert not s.outstanding_before, (
                f'seed {seed}: update {s.update_id} to {s.station} at t={s.time} '
                f'sent while {list(s.outstanding_before)} unacknowledged')


def test_next_update_sent_only_after_previous_acknowledgement_delivered():
    for seed in SEEDS:
        sim = _run(seed)
        for station in STATIONS:
            acks = {a.update_id: a for a in _acks_from(sim, station)}
            sends = _sends_to(sim, station)
            for prev, nxt in zip(sends, sends[1:]):
                ack = acks.get(prev.update_id)
                assert ack is not None and ack.delivered_at is not None, (
                    f'seed {seed}: update {prev.update_id} to {station} never acknowledged')
                assert ack.delivered_at <= nxt.time, (
                    f'seed {seed}: update {nxt.update_id} to {station} sent at t={nxt.time}, '
                    f'before acknowledgement of {prev.update_id} at t={ack.delivered_at}')


def test_newer_price_during_flight_waits_for_acknowledgement():
    station = STATIONS[0]
    sim = Simulation(7, _make_server)
    while not _sends_to(sim, station):
        assert sim.step(), f'no update was sent to {station}'
    first = _sends_to(sim, station)[0]

    sim.server.set_desired_price(station, first.price + 1000)
    assert len(_sends_to(sim, station)) == 1, (
        'a newer price triggered a second update while the first was unacknowledged')

    sim.run_until_idle()
    acks = [a for a in _acks_from(sim, station) if a.update_id == first.update_id]
    assert acks and acks[0].delivered_at is not None, 'first update was never acknowledged'
    ack_time = acks[0].delivered_at
    later = [s for s in _sends_to(sim, station) if s.update_id > first.update_id]
    assert later, f'newer price for {station} was never sent after the acknowledgement'
    assert all(s.time >= ack_time for s in later), (
        f'update {later[0].update_id} sent at t={later[0].time}, '
        f'before acknowledgement of {first.update_id} at t={ack_time}')


def test_update_identifiers_strictly_increase_per_station():
    for seed in SEEDS:
        sim = _run(seed)
        for station in STATIONS:
            ids = [s.update_id for s in _sends_to(sim, station)]
            assert all(b > a for a, b in zip(ids, ids[1:])), (
                f'seed {seed}: update identifiers to {station} not strictly increasing: {ids}')


def test_each_acknowledgement_matches_exactly_one_outstanding_update():
    for seed in SEEDS:
        sim = _run(seed)
        for station in STATIONS:
            sent = {s.update_id: s for s in _sends_to(sim, station)}
            acks = _acks_from(sim, station)
            ids = [a.update_id for a in acks]
            assert len(ids) == len(set(ids)), (
                f'seed {seed}: {station} acknowledged an update twice: {ids}')
            assert set(ids) <= set(sent), (
                f'seed {seed}: {station} acknowledged updates never sent: '
                f'{sorted(set(ids) - set(sent))}')
            assert set(ids) == set(sent), (
                f'seed {seed}: {station} updates never acknowledged: '
                f'{sorted(set(sent) - set(ids))}')
            for a in acks:
                assert a.delivered_at is not None and a.delivered_at >= sent[a.update_id].time, (
                    f'seed {seed}: acknowledgement of update {a.update_id} to {station} '
                    f'precedes its send')


def test_at_most_one_unacknowledged_update_per_station_at_every_step():
    for seed in SEEDS[:3]:
        sim = Simulation(seed, _make_server)
        while sim.step():
            for station in STATIONS:
                acked = {a.update_id for a in _acks_from(sim, station) if a.delivered_at is not None}
                unacked = [s.update_id for s in _sends_to(sim, station) if s.update_id not in acked]
                assert len(unacked) <= 1, (
                    f'seed {seed} t={sim.now}: {station} has unacknowledged updates {unacked}')
