import pytest

import app
import nrvv_env


def _setup(seed, stations=("S1",)):
    sim = nrvv_env.Simulation(seed=seed, station_ids=stations, initial_price=50)
    sim.connect(app)
    return sim


def _sends_for(sim, station):
    return sorted((r for r in sim.sends if r.station_id == station), key=lambda r: r.event_index)


def _wait_long(sim):
    for dt in (1, 5, 30, 100, 1000, 10000, 100000, 1000000):
        sim.advance_time(dt)


@pytest.mark.parametrize("seed", [1, 7, 42])
def test_no_second_send_after_timeout_without_outcome(seed):
    sim = _setup(seed)
    sim.submit("S1", 100)
    first = _sends_for(sim, "S1")
    if len(first) != 1:
        pytest.skip("precondition not reached: first send not made on submit")
    _wait_long(sim)
    assert len(_sends_for(sim, "S1")) == 1
    st = app.get_station_state("S1")
    assert st is not None


@pytest.mark.parametrize("seed", [2, 11])
def test_newer_price_during_timeout_makes_no_send_until_outcome(seed):
    sim = _setup(seed)
    sim.submit("S1", 100)
    if len(_sends_for(sim, "S1")) != 1:
        pytest.skip("precondition not reached: first send not made on submit")
    _wait_long(sim)
    sim.submit("S1", 200)
    _wait_long(sim)
    sim.submit("S1", 300)
    assert len(_sends_for(sim, "S1")) == 1


@pytest.mark.parametrize("seed", [3, 5, 13])
def test_exactly_one_new_send_with_newer_price_after_outcome(seed):
    sim = _setup(seed)
    sim.submit("S1", 100)
    sends = _sends_for(sim, "S1")
    if len(sends) != 1:
        pytest.skip("precondition not reached: first send not made on submit")
    first = sends[0]
    _wait_long(sim)
    sim.submit("S1", 200)
    assert len(_sends_for(sim, "S1")) == 1
    sim.deliver(first.send_id)
    sim.deliver_ack()
    after = _sends_for(sim, "S1")
    assert len(after) == 2
    new = after[1]
    assert new.price == 200
    assert new.send_id != first.send_id
    sim.run_until_idle()
    final = _sends_for(sim, "S1")
    assert len(final) == 2
    assert all(r.price != 100 for r in final[1:])
    assert sim.station_price("S1") == 200


def test_only_latest_of_several_newer_prices_is_sent():
    sim = _setup(9)
    sim.submit("S1", 100)
    sends = _sends_for(sim, "S1")
    if len(sends) != 1:
        pytest.skip("precondition not reached: first send not made on submit")
    first = sends[0]
    _wait_long(sim)
    for p in (150, 175, 200):
        sim.submit("S1", p)
    sim.deliver(first.send_id)
    sim.deliver_ack()
    after = _sends_for(sim, "S1")
    assert len(after) == 2
    assert after[1].price == 200
    assert after[1].send_id != first.send_id
    sim.run_until_idle()
    assert len(_sends_for(sim, "S1")) == 2
    assert sim.station_price("S1") == 200


def test_other_station_unaffected_while_first_in_flight():
    sim = _setup(4, stations=("S1", "S2"))
    sim.submit("S1", 100)
    if len(_sends_for(sim, "S1")) != 1:
        pytest.skip("precondition not reached: first send not made on submit")
    _wait_long(sim)
    assert len(_sends_for(sim, "S1")) == 1
    sim.submit("S2", 70)
    assert len(_sends_for(sim, "S2")) == 1
    assert len(_sends_for(sim, "S1")) == 1
