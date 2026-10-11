"""GASV4ELMA-47: the send decision dispatches only when reachable and latest differs from last sent."""
import app
from nrvv_env import PRICES, Simulation, check

SEEDS = (1, 2, 3)


def _make(seed):
    calls = []

    def factory(dispatch):
        def port(station_id, sequence, price):
            calls.append((station_id, sequence, price))
            dispatch(station_id, sequence, price)
        return app.Server(dispatch_update=port)

    sim = Simulation(seed, factory, stations=1, stop_time=0.0)
    return sim, calls


def _field(state, *names):
    for name in names:
        if isinstance(state, dict):
            if name in state:
                return state[name]
        elif hasattr(state, name):
            return getattr(state, name)
    raise AssertionError('station state has no field among %s' % (names,))


def _latest(state):
    return _field(state, 'latest_desired', 'latestDesired')


def _last_sent_price(state):
    return _field(state, 'last_sent_price', 'lastSentPrice')


def _last_sent_seq(state):
    return _field(state, 'last_sent_seq', 'lastSentSeq')


def _outstanding(state):
    return set(_field(state, 'outstanding', 'outstanding_seqs', 'outstanding_sequences'))


def _reachable(state):
    return _field(state, 'reachable')


def _snapshot(state):
    return (_latest(state), _last_sent_price(state), _last_sent_seq(state),
            frozenset(_outstanding(state)), _reachable(state))


def _other(price):
    return PRICES[(PRICES.index(price) + 1) % len(PRICES)]


def test_first_price_on_reachable_station_is_dispatched_with_sequence_one():
    for seed in SEEDS:
        for price in PRICES:
            sim, calls = _make(seed)
            sid = sim.station_ids[0]
            sim.app.reachability_changed(sid, True)
            assert _last_sent_price(sim.app.station_state(sid)) is None

            sim.app.set_desired_price(sid, price)

            assert calls == [(sid, 1, price)]
            state = sim.app.station_state(sid)
            assert _latest(state) == price
            assert _last_sent_price(state) == price
            assert _last_sent_seq(state) == 1
            assert _outstanding(state) == {1}
            # next sequence number is N+1: the next distinct price goes out as sequence 2
            other = _other(price)
            sim.app.set_desired_price(sid, other)
            assert calls[-1] == (sid, 2, other)
            assert not any(check(sim).values())


def test_repeat_of_last_sent_price_on_reachable_station_is_not_dispatched():
    for seed in SEEDS:
        for price in PRICES:
            sim, calls = _make(seed)
            sid = sim.station_ids[0]
            sim.app.reachability_changed(sid, True)
            sim.app.set_desired_price(sid, price)
            assert len(calls) == 1
            before = _snapshot(sim.app.station_state(sid))

            sim.app.set_desired_price(sid, price)

            assert len(calls) == 1
            assert _snapshot(sim.app.station_state(sid)) == before
            # next sequence number was not advanced: the next distinct price is still sequence 2
            other = _other(price)
            sim.app.set_desired_price(sid, other)
            assert calls[-1] == (sid, 2, other)
            assert not any(check(sim).values())


def test_unreachable_station_is_not_dispatched_when_price_differs_from_empty_last_sent():
    for seed in SEEDS:
        for price in PRICES:
            sim, calls = _make(seed)
            sid = sim.station_ids[0]
            sim.app.reachability_changed(sid, False)

            sim.app.set_desired_price(sid, price)

            assert calls == []
            state = sim.app.station_state(sid)
            assert _latest(state) == price
            assert _last_sent_price(state) is None
            assert _reachable(state) is False


def test_unreachable_station_is_not_dispatched_when_price_differs_from_last_sent():
    for seed in SEEDS:
        for price in PRICES:
            sim, calls = _make(seed)
            sid = sim.station_ids[0]
            sim.app.reachability_changed(sid, True)
            sim.app.set_desired_price(sid, price)
            assert calls == [(sid, 1, price)]
            sim.app.reachability_changed(sid, False)
            other = _other(price)

            sim.app.set_desired_price(sid, other)

            assert calls == [(sid, 1, price)]
            state = sim.app.station_state(sid)
            assert _latest(state) == other
            assert _last_sent_price(state) == price
            assert _last_sent_seq(state) == 1
            assert _reachable(state) is False
