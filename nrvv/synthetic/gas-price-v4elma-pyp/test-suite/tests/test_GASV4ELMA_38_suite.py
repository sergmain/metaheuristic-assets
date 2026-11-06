"""GASV4ELMA-38: suppress duplicate sends of the price already sent (GASV4ELMA-13).

Drives the server only through nrvv_env: the simulation has no scheduled
environment events here (stop_time=0, horizon=0), so the test calls the
server's inbound operations directly and reads the dispatch trace.
"""
import app
from nrvv_env import PRICES, Simulation, check


def _make_sim(seed, stations=2):
    return Simulation(seed, server_factory=lambda dispatch: app.Server(dispatch_update=dispatch),
                      stations=stations, stop_time=0.0, horizon=0.0)


def _dispatches(sim):
    return [r for r in sim.trace if r.kind == 'dispatch']


def test_same_price_as_last_sent_dispatches_nothing():
    for seed in (1, 2, 3):
        sim = _make_sim(seed)
        sid = sim.station_ids[0]
        for price in PRICES:
            assert sim.app.set_desired_price(sid, price) == 'Accepted'
            sent = _dispatches(sim)
            assert sent[-1].price == price
            # latestDesired == lastSentPrice now: repeated decisions must send nothing
            for _ in range(3):
                assert sim.app.set_desired_price(sid, price) == 'Accepted'
                assert _dispatches(sim) == sent


def test_ack_of_last_sent_price_triggers_single_resend():
    for seed in (4, 5, 6):
        for price in PRICES:
            sim = _make_sim(seed)
            sid = sim.station_ids[0]
            assert sim.app.set_desired_price(sid, price) == 'Accepted'
            assert [(r.seq, r.price) for r in _dispatches(sim)] == [(1, price)]

            # latestDesired still equals lastSentPrice: no send yet
            assert sim.app.set_desired_price(sid, price) == 'Accepted'
            before = _dispatches(sim)

            # acknowledgement of the last sent price: the only send is the D6 resend
            sim.app.acknowledgement_received(sid, 1, price)
            after = _dispatches(sim)
            assert len(after) == len(before) + 1
            assert after[:len(before)] == before
            resend = after[-1]
            assert (resend.station, resend.seq, resend.price) == (sid, 2, price)
            assert check(sim)['sequence'] == []
