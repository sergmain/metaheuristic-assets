import app
from nrvv_env import Simulation
from nrvv_env.simulation import _status_fields

SEEDS = (0, 1, 2, 3, 4)
C0 = 10
P1 = 20
P2 = 30
ACK_STEP_LIMIT = 300


def _new_service():
    if callable(getattr(app, 'set_desired_price', None)):
        return app
    for name in dir(app):
        candidate = getattr(app, name)
        if isinstance(candidate, type) and callable(getattr(candidate, 'set_desired_price', None)):
            return candidate()
    raise AssertionError('app offers no set_desired_price operation')


def _sim(service, seed, stations):
    return Simulation(service, seed, stations, loss=0.0, max_outages_per_station=0)


def _state(sim, station):
    return _status_fields(sim.get_station_status(station))


def _settle(sim, station, price):
    sim.set_desired_price(station, price)
    sim.quiesce()


def _step_until_new_ack(sim, count_before):
    for _ in range(ACK_STEP_LIMIT):
        sim.step()
        if len(sim.acks) > count_before:
            return sim.acks[count_before:]
    raise AssertionError('no acknowledgement arrived within %d ticks' % ACK_STEP_LIMIT)


def _anomaly_counts(service):
    counts = {}
    for name in dir(service):
        if 'anomal' not in name.lower():
            continue
        value = getattr(service, name)
        if callable(value):
            try:
                value = value()
            except Exception:
                continue
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            counts[name] = value
        elif isinstance(value, dict):
            counts[name] = sum(v for v in value.values() if isinstance(v, int) and not isinstance(v, bool))
    return counts


def _anomaly_deltas(before, after):
    return {name: after.get(name, 0) - before.get(name, 0) for name in set(before) | set(after)}


def test_ack_with_in_flight_update_sets_confirmed_price_and_clears_in_flight(tmp_path):
    for seed in SEEDS:
        station = '%s-%d' % (tmp_path.name, seed)
        sim = _sim(_new_service(), seed, [station])
        _settle(sim, station, C0)
        sim.set_desired_price(station, P1)
        desired, confirmed, in_flight, _ = _state(sim, station)
        assert (desired, confirmed, in_flight) == (P1, C0, P1)
        new_acks = _step_until_new_ack(sim, len(sim.acks))
        assert [(a.station, a.price) for a in new_acks] == [(station, P1)]
        desired, confirmed, in_flight, sent_at = _state(sim, station)
        assert confirmed == P1
        assert in_flight is None
        assert sent_at is None


def test_ack_with_in_flight_update_reevaluates_dispatch_once(tmp_path):
    for seed in SEEDS:
        station = '%s-%d' % (tmp_path.name, seed)
        sim = _sim(_new_service(), seed, [station])
        _settle(sim, station, C0)
        sim.set_desired_price(station, P1)
        sim.set_desired_price(station, P2)
        desired, confirmed, in_flight, _ = _state(sim, station)
        assert (desired, confirmed, in_flight) == (P2, C0, P1)
        sends_before = len(sim.sent_updates(station))
        _step_until_new_ack(sim, len(sim.acks))
        sends = [u.price for u in sim.sent_updates(station)[sends_before:]]
        assert sends == [P2]
        desired, confirmed, in_flight, _ = _state(sim, station)
        assert confirmed == P1
        assert in_flight == P2


def test_ack_without_in_flight_update_is_discarded_and_counted_as_anomaly(tmp_path):
    for seed in SEEDS:
        station = '%s-%d' % (tmp_path.name, seed)
        service = _new_service()
        sim = _sim(service, seed, [station])
        _settle(sim, station, C0)
        before = _state(sim, station)
        assert before[1:3] == (C0, None)
        sends_before = len(sim.sent_updates(station))
        anomalies_before = _anomaly_counts(service)
        sim._ack_receiver(station)
        after = _state(sim, station)
        assert after[0] == before[0]
        assert after[1:3] == (C0, None)
        assert len(sim.sent_updates(station)) == sends_before
        deltas = _anomaly_deltas(anomalies_before, _anomaly_counts(service))
        assert any(d == 1 for d in deltas.values())
        assert all(d in (0, 1) for d in deltas.values())


def test_acknowledgements_are_processed_in_arrival_order(tmp_path):
    for seed in SEEDS:
        stations = ['%s-%d-%d' % (tmp_path.name, seed, i) for i in range(3)]
        sim = Simulation(_new_service(), seed, stations)
        sim.run_scenario(60)
        for station in stations:
            acked = [a for a in sim.acks if a.station == station]
            delivered = [d for d in sim.deliveries if d.station == station]
            assert [a.price for a in acked] == [d.price for d in delivered]
            assert [a.receipt_time for a in acked] == [d.time for d in delivered]
            assert [a.time for a in acked] == sorted(a.time for a in acked)
            desired, confirmed, in_flight, _ = _state(sim, station)
            assert in_flight is None
            assert confirmed == desired == sim.last_desired[station]
