'''GASV4R12A-17: the latest received acknowledgement defines the acknowledged price.'''
from nrvv_env import Simulation

import app

SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)
MAX_TICKS = 500


def _field(status, names, label):
    for name in names:
        if isinstance(status, dict) and name in status:
            return status[name]
        if hasattr(status, name):
            return getattr(status, name)
    raise AssertionError('status has no {}: tried {}'.format(label, names))


def _acked_price(status):
    return _field(status, ('latest_acknowledged_price', 'acknowledged_price', 'latest_acknowledged',
                           'acked_price', 'latest_ack_price'), 'latest acknowledged price')


def _desired_version(status):
    return _field(status, ('desired_version',), 'desired version')


def _in_flight(status):
    return list(_field(status, ('in_flight_versions', 'versions_in_flight', 'in_flight'), 'in-flight versions'))


def _replay(seed):
    '''Step one seeded run; yield per tick (sim, status before the tick, status after it, acks delivered in it).'''
    sim = Simulation(seed)
    sim.attach(lambda send: app.Server(send_update=send))
    prev = {sid: sim.server.query_station_status(sid) for sid in sim.station_ids}
    for _ in range(MAX_TICKS):
        n_acks = len(sim.acks)
        sim.step()
        now = {rec.station: rec.result for rec in sim.queries[-len(sim.station_ids):]}
        yield sim, prev, now, sim.acks[n_acks:]
        prev = now
        if sim.now >= sim.stop_tick and not sim.in_flight():
            return
    raise AssertionError('transport still busy after {} ticks'.format(MAX_TICKS))


def test_latest_acknowledged_price_is_last_delivered_displayed_price():
    delivered = 0
    for seed in SEEDS:
        for sim, _prev, now, new_acks in _replay(seed):
            for sid in sim.station_ids:
                mine = [ack for ack in new_acks if ack.station == sid]
                if mine:
                    delivered += len(mine)
                    assert _acked_price(now[sid]) == mine[-1].displayed, (seed, sim.now, sid)
    assert delivered > 0


def test_stale_acknowledgements_still_overwrite_latest_price():
    stale = 0
    for seed in SEEDS:
        for sim, prev, now, new_acks in _replay(seed):
            for sid in sim.station_ids:
                mine = [ack for ack in new_acks if ack.station == sid]
                for ack in mine:
                    if ack.version not in _in_flight(prev[sid]) or ack.version < _desired_version(prev[sid]):
                        stale += 1
                if mine:
                    assert _acked_price(now[sid]) == mine[-1].displayed, (seed, sim.now, sid)
    assert stale > 0
