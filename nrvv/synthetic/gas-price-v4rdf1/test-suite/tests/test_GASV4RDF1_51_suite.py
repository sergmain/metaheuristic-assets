import collections.abc

import app
import nrvv_env


STATION = 'S1'
P1 = 'P1'
P2 = 'P2'
SEEDS = range(1, 301)


def _make_server(send_update, send_pricing_notice):
    classes = {obj for obj in vars(app).values()
               if isinstance(obj, type)
               and all(callable(getattr(obj, m, None))
                       for m in ('set_desired_price', 'receive_acknowledgement', 'query_station_state'))}
    assert len(classes) == 1, f'expected one server class in app, found {sorted(c.__name__ for c in classes)}'
    return next(iter(classes))(send_update, send_pricing_notice)


def _scenario(seed):
    return nrvv_env.Simulation(seed, _make_server, [STATION], script=[[(STATION, P1), (STATION, P2)]])


def _qualifying(seed):
    # Runs until the first acknowledgement arrives. The run qualifies when P1 was sent,
    # P2 was set after P1 was sent, and the first acknowledgement is P1's.
    sim = _scenario(seed)
    while not sim.delivered_acks and not sim.quiet:
        sim.step()
    if not sim.delivered_acks or len(sim.client_calls) != 2:
        return None
    p1_sent = [s for s in sim.sent if s.price == P1]
    p2_call = sim.client_calls[1]
    ack = sim.delivered_acks[0]
    if len(p1_sent) != 1 or not p1_sent[0].step < p2_call.step < ack.step:
        return None
    if (ack.price, ack.update_id) != (P1, p1_sent[0].update_id):
        return None
    return sim


def _qualifying_runs(count=3):
    runs = []
    for seed in SEEDS:
        sim = _qualifying(seed)
        if sim is not None:
            runs.append(sim)
            if len(runs) == count:
                break
    assert runs, 'no seed sent P1, set P2 before P1 was acknowledged, and acknowledged P1 first'
    return runs


def _state(result):
    # QueryStationState returns confirmed price, desired price and outstanding count.
    names = ('confirmed', 'desired', 'outstanding')
    if isinstance(result, collections.abc.Mapping):
        keyed = {str(k).lower(): v for k, v in result.items()}
        return tuple(next(v for k, v in keyed.items() if word in k)
                     for word in ('confirm', 'desire', 'outstanding'))
    if all(hasattr(result, n) for n in names):
        return tuple(getattr(result, n) for n in names)
    return tuple(result)


def test_superseded_price_is_never_resent_after_newer_is_set():
    for sim in _qualifying_runs():
        p2_call = sim.client_calls[1]
        sim.run(max_steps=1000)
        sent_after = [s.price for s in sim.sent if s.step >= p2_call.step]
        assert sent_after.count(P2) == 1
        assert P1 not in sent_after
        assert [s.price for s in sim.sent].count(P1) == 1
        received_p2 = [d.price for d in sim.delivered_updates if d.step > p2_call.step]
        assert received_p2.count(P2) == 1


def test_superseded_ack_clears_only_its_entry():
    for sim in _qualifying_runs():
        confirmed, desired, outstanding = _state(sim.query(STATION))
        assert confirmed == P1
        assert desired == P2
        assert outstanding == 1


def test_newer_price_confirmed_only_by_its_own_ack():
    for sim in _qualifying_runs():
        sim.run(max_steps=1000)
        assert [a.price for a in sim.delivered_acks] == [P1, P2]
        assert _state(sim.query(STATION)) == (P2, P2, 0)
