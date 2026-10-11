"""GASV4ELMA-43: the server relies only on updates and acknowledgements, never on station changes."""
import app
from nrvv_env import PRICES, Record, Simulation

_RECONNECT_SEEDS = (3, 11, 29)


def _factory(dispatch):
    return app.Server(dispatch_update=dispatch)


def _simulation(seed, horizon):
    # One station and no random price schedule; reachability changes only if horizon allows them.
    return Simulation(seed, _factory, stations=1, stop_time=0.0, horizon=horizon)


def _set(sim, station_id, price):
    rec = Record(sim.now, 'set', station_id, price=price)
    sim.trace.append(rec)
    rec.detail = sim.app.set_desired_price(station_id, price)
    assert rec.detail == 'Accepted'
    return rec


def _ack(sim, station_id, sequence, price):
    sim.trace.append(Record(sim.now, 'ack', station_id, sequence, price))
    sim.app.acknowledgement_received(station_id, sequence, price)


def _assert_outbound_are_price_updates(sim, station_id):
    # The outbound port carries only DispatchUpdate(station, sequence, price).
    dispatches = [r for r in sim.trace if r.kind == 'dispatch' and r.station == station_id]
    assert dispatches, 'server dispatched nothing to the station'
    assert [r.seq for r in dispatches] == list(range(1, len(dispatches) + 1))
    assert all(r.price in PRICES for r in dispatches)


def _redispatched_after(sim, mark, station_id, price):
    return [r for r in sim.trace[mark:]
            if r.kind == 'dispatch' and r.station == station_id and r.price == price]


def test_stale_ack_makes_server_redispatch_latest_price():
    sim = _simulation(seed=7, horizon=0.0)
    sid = sim.station_ids[0]
    _set(sim, sid, 100)
    _set(sim, sid, 105)
    mark = len(sim.trace)
    _ack(sim, sid, 1, 100)  # older sequence number and older price
    sim.run()
    assert _redispatched_after(sim, mark, sid, 105), \
        'no dispatch of the latest price after a stale acknowledgement'
    _assert_outbound_are_price_updates(sim, sid)


def test_reconnect_redispatches_latest_price_and_inbound_is_only_acks():
    for seed in _RECONNECT_SEEDS:
        _check_reconnect(seed)


def _check_reconnect(seed):
    sim = _simulation(seed=seed, horizon=20.0)
    sid = sim.station_ids[0]
    # The first scheduled reachability change always takes the station offline.
    down_time, goes_reachable = sim.reach_schedule[sid][0]
    assert goes_reachable is False

    _set(sim, sid, 100)
    _set(sim, sid, 105)
    mark = len(sim.trace)
    _ack(sim, sid, 1, 100)  # stale: older sequence number and price
    assert _redispatched_after(sim, mark, sid, 105), \
        'no dispatch of the latest price after a stale acknowledgement (seed %s)' % seed

    sim.run_until(down_time)
    assert not sim.stations[sid].reachable

    down_mark = len(sim.trace)
    _set(sim, sid, 110)  # latest price arrives while the station is unreachable
    up_time = down_time + 0.5
    sim.force_reachable(sid, up_time)
    sim.run_until(up_time)
    while_down = [r for r in sim.trace[down_mark:] if r.kind == 'dispatch' and r.time < up_time]
    assert not while_down, 'server dispatched to an unreachable station (seed %s)' % seed
    sim.run()

    assert [r for r in sim.trace[down_mark:]
            if r.kind == 'dispatch' and r.station == sid and r.time >= up_time and r.price == 110], \
        'latest price not dispatched after the station became reachable (seed %s)' % seed

    inbound = [r for r in sim.trace if r.kind == 'ack']
    assert inbound, 'no acknowledgements recorded (seed %s)' % seed
    assert all(r.station == sid and isinstance(r.seq, int) and r.price is not None
               for r in inbound), 'inbound traffic other than acknowledgements (seed %s)' % seed
    _assert_outbound_are_price_updates(sim, sid)
