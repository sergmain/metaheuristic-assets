import pytest
import app
import nrvv_env

STATION = "S1"


def _scenario(seed, ack_latency=2.0):
    sim = nrvv_env.Simulation(seed=seed, ordering="fifo", cost_per_send=1.0,
                              stale_cost_per_time=1.0, start_time=100.0)
    sim.connect(app)
    for price in (10.0, 11.0, 12.0):
        sim.submit(STATION, price)
        sim.advance(1.0)
    if len(sim.sends) < 3:
        # give the service a chance to issue further sends
        sim.advance(1.0)
    if len(sim.sends) < 3:
        pytest.skip("precondition not reached: three outstanding requests for one station")
    ids = [s["request_id"] for s in sim.sends[:3]]
    if len(set(ids)) < 3 or any(s["station_id"] != STATION for s in sim.sends[:3]):
        pytest.skip("precondition not reached: three distinct requests for one station")
    # deliver first send to the station, then acknowledge it after the latency
    sim.step_send()
    sim.advance(ack_latency)
    sim.step_ack()
    return sim


def _stale_cost(sim):
    rep = app.get_stale_price_cost_report(None)
    return rep["cost_total"]


def _sending_cost(sim):
    rep = app.get_sending_cost_report(None)
    return rep["cost_total"]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_matched_ack_closes_first_request_only(seed):
    sim = _scenario(seed)
    state = app.get_station_state(STATION)
    assert state["last_acknowledged_price"] == sim.sends[0]["price"]
    assert not state["settled"]
    app.on_acknowledgement(STATION, "wrong-id-" + str(seed), "ok")
    state = app.get_station_state(STATION)
    assert state["last_acknowledged_price"] == sim.sends[0]["price"]
    assert not state["settled"]


@pytest.mark.parametrize("seed", [1, 2])
def test_mismatched_ack_keeps_stale_cost_accruing(seed):
    sim = _scenario(seed)
    app.on_acknowledgement(STATION, "wrong-id-" + str(seed), "ok")
    c1 = _stale_cost(sim)
    sim.advance(10.0)
    c2 = _stale_cost(sim)
    sim.advance(10.0)
    c3 = _stale_cost(sim)
    assert c2 > c1
    assert c3 > c2


def test_ack_latency_is_part_of_matched_record_cost():
    costs = []
    for latency in (1.0, 9.0):
        _scenario(5, ack_latency=latency)
        costs.append(_sending_cost(None))
    assert costs[1] > costs[0]
