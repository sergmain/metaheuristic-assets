"""GASV4ELMA-51: resend the latest price to each station that has not confirmed it (GASV4ELMA-33)."""
import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)
OLD_PRICE = 100
LATEST_PRICE = 110


def _server_factory(dispatch):
    return app.Server(dispatch_update=dispatch)


def _run_scenario(seed):
    """Station 2 confirms the latest price; station 1 acks the older price after the latest is set;
    station 3 has never reported. Returns (sim, mark), where mark indexes the trace when the latest
    price is set.
    """
    sim = Simulation(seed, _server_factory, stations=3, stop_time=0.0, horizon=0.0)
    s1, s2, s3 = sim.station_ids
    sim.app.set_desired_price(s2, LATEST_PRICE)
    sim.run()
    older_mark = len(sim.trace)
    sim.app.set_desired_price(s1, OLD_PRICE)
    # advance only until station 1 has displayed the older price, so its acknowledgement is still pending
    while not any(r.kind == 'display' and r.station == s1 for r in sim.trace[older_mark:]):
        if not sim.step():
            raise AssertionError('station-1 never displayed the older price')
    mark = len(sim.trace)
    sim.app.set_desired_price(s1, LATEST_PRICE)
    sim.app.set_desired_price(s3, LATEST_PRICE)
    sim.run()
    if not any(r.kind == 'ack' and r.station == s1 and r.price == OLD_PRICE for r in sim.trace[mark:]):
        raise AssertionError('seed %d: no acknowledgement of the older price reached the server' % seed)
    return sim, mark


def test_older_ack_triggers_resend_of_latest_price_to_that_station():
    for seed in SEEDS:
        sim, mark = _run_scenario(seed)
        s1 = sim.station_ids[0]
        ack_at = [i for i, r in enumerate(sim.trace)
                  if i >= mark and r.kind == 'ack' and r.station == s1 and r.price == OLD_PRICE]
        resent_after = [i for i, r in enumerate(sim.trace)
                        if i > ack_at[0] and r.kind == 'dispatch' and r.station == s1 and r.price == LATEST_PRICE]
        assert resent_after, 'seed %d: no latest-price update to station-1 after its older-price ack' % seed


def test_every_unconfirmed_station_is_sent_the_latest_price():
    for seed in SEEDS:
        sim, mark = _run_scenario(seed)
        s1, _, s3 = sim.station_ids
        for sid in (s1, s3):
            sent = [r.price for r in sim.trace[mark:] if r.kind == 'dispatch' and r.station == sid]
            assert sent, 'seed %d: no update sent to %s' % (seed, sid)
            assert LATEST_PRICE in sent, 'seed %d: %s never sent the latest price' % (seed, sid)


def test_station_that_confirmed_latest_price_gets_no_update():
    for seed in SEEDS:
        sim, mark = _run_scenario(seed)
        s2 = sim.station_ids[1]
        sent = [r for r in sim.trace[mark:] if r.kind == 'dispatch' and r.station == s2]
        assert not sent, 'seed %d: confirmed station-2 received %d update(s)' % (seed, len(sent))


def test_no_update_after_latest_set_carries_older_price():
    for seed in SEEDS:
        sim, mark = _run_scenario(seed)
        wrong = [r for r in sim.trace[mark:] if r.kind == 'dispatch' and r.price != LATEST_PRICE]
        assert not wrong, 'seed %d: update(s) with a non-latest price: %r' % (seed, wrong)
