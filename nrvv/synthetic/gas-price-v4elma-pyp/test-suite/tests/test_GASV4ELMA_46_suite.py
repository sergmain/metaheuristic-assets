"""Tests for GASV4ELMA-4: send an update when the desired price changes."""
import app
from nrvv_env import Simulation

SEEDS = (1, 7, 42)
PRICE_PAIRS = (('1.50', '1.60'), (100, 115), ('2.10', '2.05'))


def _server(dispatch):
    return app.Server(dispatch_update=dispatch)


def _new_sim(seed):
    # stop_time=0 and horizon=0 schedule no random price or reachability events,
    # so the test itself makes every SetDesiredPrice call
    return Simulation(seed, _server, stations=3, stop_time=0.0, horizon=0.0)


def _dispatches(sim, station_id, since=0):
    return [r for r in sim.trace[since:] if r.kind == 'dispatch' and r.station == station_id]


def test_price_change_sends_update_with_new_price():
    for seed in SEEDS:
        for p1, p2 in PRICE_PAIRS:
            sim = _new_sim(seed)
            sid = sim.station_ids[1]
            sim.app.set_desired_price(sid, p1)
            sim.run()  # the P1 update is delivered and acknowledged
            sent = _dispatches(sim, sid)
            assert sent and sent[-1].price == p1, 'P1 update not sent before the change (seed %s)' % seed
            mark = len(sim.trace)
            sim.app.set_desired_price(sid, p2)
            sim.run()
            after = _dispatches(sim, sid, mark)
            assert after, 'no update sent after the change (seed %s, P2=%r)' % (seed, p2)
            assert all(r.price == p2 for r in after), \
                'update after the change carries %r, expected %r (seed %s)' % (after[-1].price, p2, seed)


def test_change_sent_while_previous_update_unacknowledged():
    for seed in SEEDS:
        for p1, p2 in PRICE_PAIRS:
            sim = _new_sim(seed)
            sid = sim.station_ids[0]
            sim.app.set_desired_price(sid, p1)  # P1 dispatched, delivery still pending
            sent = _dispatches(sim, sid)
            assert sent and sent[-1].price == p1, 'P1 update not sent before the change (seed %s)' % seed
            mark = len(sim.trace)
            sim.app.set_desired_price(sid, p2)
            sim.run()
            after = _dispatches(sim, sid, mark)
            assert after, 'no update sent after the change (seed %s, P2=%r)' % (seed, p2)
            assert all(r.price == p2 for r in after), \
                'update after the change carries %r, expected %r (seed %s)' % (after[-1].price, p2, seed)
