import itertools

import pytest

import app
import nrvv_env
from nrvv_env import Simulation

_counter = itertools.count()


def _station(tag):
    return "st-%s-%d" % (tag, next(_counter))


def _make(seed=1):
    sim = Simulation(seed=seed, ordering="fifo")
    sim.connect(app)
    return sim


def _sends_for(sim, sid):
    return [s for s in sim.sends if s["station_id"] == sid]


def _acks_for(sim, sid):
    return [a for a in sim.acknowledgements if a["station_id"] == sid]


def _outstanding(sim, sid):
    return len(_sends_for(sim, sid)) - len(_acks_for(sim, sid))


def _ack_next(sim):
    assert sim.step_send()
    assert sim.step_ack()


def test_no_second_send_while_first_unacknowledged():
    sim = _make()
    sid = _station("a")
    sim.submit(sid, 100)
    assert len(_sends_for(sim, sid)) == 1
    sim.advance(1)
    sim.submit(sid, 110)
    assert len(_sends_for(sim, sid)) == 1
    sim.advance(1)
    sim.submit(sid, 120)
    assert len(_sends_for(sim, sid)) == 1
    # even after the send was delivered but not yet acknowledged
    sim.step_send()
    assert len(_sends_for(sim, sid)) == 1


def test_after_ack_exactly_one_new_send_with_newest_price():
    sim = _make()
    sid = _station("b")
    sim.submit(sid, 100)
    sim.advance(1)
    sim.submit(sid, 110)
    first = _sends_for(sim, sid)[0]
    _ack_next(sim)
    sends = _sends_for(sim, sid)
    assert len(sends) == 2
    second = sends[1]
    assert second["price"] == 110
    assert second["price"] != 100
    assert second["version"] != first["version"]
    assert second["version"] > first["version"]
    assert second["request_id"] != first["request_id"]


def test_coalesces_intermediate_prices():
    sim = _make()
    sid = _station("c")
    sim.submit(sid, 100)
    for p in (101, 102, 103):
        sim.advance(1)
        sim.submit(sid, p)
    assert len(_sends_for(sim, sid)) == 1
    _ack_next(sim)
    sends = _sends_for(sim, sid)
    assert len(sends) == 2
    assert sends[1]["price"] == 103


def test_rule_holds_again_after_second_send_acknowledged():
    sim = _make()
    sid = _station("d")
    sim.submit(sid, 100)
    sim.advance(1)
    sim.submit(sid, 110)
    _ack_next(sim)
    assert len(_sends_for(sim, sid)) == 2
    sim.advance(1)
    sim.submit(sid, 120)
    assert len(_sends_for(sim, sid)) == 2
    _ack_next(sim)
    sends = _sends_for(sim, sid)
    assert len(sends) == 3
    assert sends[2]["price"] == 120
    assert sends[2]["version"] > sends[1]["version"]
    assert _outstanding(sim, sid) == 1


def test_two_stations_send_independently():
    sim = _make()
    s1 = _station("e1")
    s2 = _station("e2")
    sim.submit(s1, 100)
    sim.submit(s2, 200)
    assert len(_sends_for(sim, s1)) == 1
    assert len(_sends_for(sim, s2)) == 1
    assert _sends_for(sim, s1)[0]["price"] == 100
    assert _sends_for(sim, s2)[0]["price"] == 200
    sim.advance(1)
    sim.submit(s1, 101)
    sim.submit(s2, 201)
    assert len(_sends_for(sim, s1)) == 1
    assert len(_sends_for(sim, s2)) == 1


def test_ack_of_one_station_does_not_affect_other():
    sim = _make()
    s1 = _station("f1")
    s2 = _station("f2")
    sim.submit(s1, 100)
    sim.submit(s2, 200)
    sim.advance(1)
    sim.submit(s1, 101)
    sim.submit(s2, 201)
    # acks come in request order: s1's send first
    _ack_next(sim)
    assert len(_sends_for(sim, s1)) == 2
    assert _sends_for(sim, s1)[1]["price"] == 101
    assert len(_sends_for(sim, s2)) == 1
    _ack_next(sim)
    assert len(_sends_for(sim, s2)) == 2
    assert _sends_for(sim, s2)[1]["price"] == 201


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_at_most_one_unconfirmed_send_per_station_always(seed):
    sim = Simulation(seed=seed)
    sim.connect(app)
    sids = [_station("g%d" % i) for i in range(3)]
    rng = sim.rng
    price = 100
    for _ in range(40):
        action = rng.random()
        if action < 0.5:
            price += 1
            sim.advance(1)
            sim.submit(rng.choice(sids), price)
        else:
            sim.step()
        for sid in sids:
            assert _outstanding(sim, sid) <= 1
    sim.run_until_idle()
    for sid in sids:
        assert _outstanding(sim, sid) <= 1
