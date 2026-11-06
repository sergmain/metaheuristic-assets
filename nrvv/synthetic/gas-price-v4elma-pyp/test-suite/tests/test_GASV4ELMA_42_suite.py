# GASV4ELMA-42: a price replaced while a station is unreachable is never dispatched.
import app
from nrvv_env import PRICES, Record, Simulation, check

P1, P2, P3 = PRICES[0], PRICES[1], PRICES[2]
SEEDS = (1, 7, 42)


def _set(sim, sid, price):
    rec = Record(sim.now, 'set', sid, price=price)
    sim.trace.append(rec)
    rec.detail = sim.app.set_desired_price(sid, price)
    return rec.detail


def _scenario(seed):
    sim = Simulation(seed=seed, server_factory=lambda dispatch: app.Server(dispatch_update=dispatch),
                     stations=1, stop_time=0.0, horizon=0.0)
    sid = sim.station_ids[0]
    sim.stations[sid].reachable = False
    sim.trace.append(Record(sim.now, 'reach', sid, detail=False))
    sim.app.reachability_changed(sid, False)

    results = [_set(sim, sid, P1), _set(sim, sid, P2)]
    sim.run_until(sim.now + 5.0)
    reconnect = len(sim.trace)
    sim.force_reachable(sid, sim.now)
    sim.run_until(sim.now)
    sim.run()

    mark = len(sim.trace)
    results.append(_set(sim, sid, P3))
    same_call = [r for r in sim.trace[mark:] if r.kind == 'dispatch']
    sim.run()
    return {'sim': sim, 'sid': sid, 'results': results, 'reconnect': reconnect, 'same_call': same_call}


def test_no_dispatch_while_station_unreachable():
    for seed in SEEDS:
        s = _scenario(seed)
        assert [r for r in s['sim'].trace[:s['reconnect']] if r.kind == 'dispatch'] == [], 'seed %d' % seed


def test_first_dispatch_after_reconnect_carries_newest_price():
    for seed in SEEDS:
        s = _scenario(seed)
        after = [r for r in s['sim'].trace[s['reconnect']:] if r.kind == 'dispatch']
        assert after, 'no dispatch after reconnection, seed %d' % seed
        assert after[0].price == P2, 'seed %d' % seed
        assert after[0].seq == 1, 'seed %d' % seed


def test_replaced_price_is_never_dispatched():
    for seed in SEEDS:
        sim = _scenario(seed)['sim']
        assert P1 not in [r.price for r in sim.trace if r.kind == 'dispatch'], 'seed %d' % seed


def test_replacement_dispatches_during_same_call_when_reachable():
    for seed in SEEDS:
        s = _scenario(seed)
        assert any(r.price == P3 for r in s['same_call']), 'seed %d' % seed


def test_replacements_are_accepted_and_run_passes_oracle():
    for seed in SEEDS:
        s = _scenario(seed)
        assert s['results'] == ['Accepted', 'Accepted', 'Accepted'], 'seed %d' % seed
        assert not any(check(s['sim']).values()), 'seed %d' % seed
