'''Requirement GASV4R12A-8: do not send updates to stations already on latest price.'''
import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3)


def _last_status(sim, station):
    for q in reversed(sim.queries):
        if q.station == station:
            return q.result
    raise AssertionError('no status query recorded for {}'.format(station))


def _acked_price(status):
    for name in ('latest_acknowledged_price', 'acknowledged_price', 'latest_acked_price', 'acked_price', 'ack_price'):
        if isinstance(status, dict) and name in status:
            return status[name]
        if hasattr(status, name):
            return getattr(status, name)
    raise AssertionError('status exposes no acknowledged price: {!r}'.format(status))


def _prepared_sim(seed):
    sim = Simulation(seed, stations=('a', 'b'), stop_tick=5, fault_window=(0, 0),
                     max_delay=3, change_rate=0.0)
    sim.attach(lambda send: app.Server(send_update=send))
    sim.source_schedule = {1: [('a', 10), ('b', 20)]}
    sim.run_until_idle()
    assert _acked_price(_last_status(sim, 'a')) == 10
    assert _acked_price(_last_status(sim, 'b')) == 20
    return sim


def test_station_on_latest_price_gets_no_update_while_other_station_does():
    for seed in SEEDS:
        sim = _prepared_sim(seed)
        acked_a = _acked_price(_last_status(sim, 'a'))
        sim.source_schedule = {sim.now + 1: [('b', 30)]}
        mark = len(sim.sends)
        sim.step()
        new = sim.sends[mark:]
        assert not [s for s in new if s.station == 'a'], 'update sent to station already on latest price'
        assert [s for s in new if s.station == 'b' and s.price == 30], 'no update sent to station behind latest price'
        assert _acked_price(_last_status(sim, 'a')) == acked_a


def test_station_already_on_latest_price_receives_no_update_over_later_ticks():
    for seed in SEEDS:
        sim = _prepared_sim(seed)
        mark = len(sim.sends)
        sim.run(10)
        assert not [s for s in sim.sends[mark:] if s.station == 'a']
        assert _acked_price(_last_status(sim, 'a')) == 10
