import pytest

import app
import nrvv_env


def _field(state, name):
    if isinstance(state, dict):
        if name in state:
            return state[name]
        camel = "".join(p if i == 0 else p.capitalize() for i, p in enumerate(name.split("_")))
        return state[camel]
    if hasattr(state, name):
        return getattr(state, name)
    camel = "".join(p if i == 0 else p.capitalize() for i, p in enumerate(name.split("_")))
    return getattr(state, camel)


def _is_accepted(result):
    if result is True:
        return True
    if isinstance(result, str):
        return result.lower() == "accepted"
    name = getattr(result, "name", None)
    if isinstance(name, str):
        return name.lower() == "accepted"
    value = getattr(result, "value", None)
    if isinstance(value, str):
        return value.lower() == "accepted"
    return False


@pytest.mark.parametrize("seed", [0, 1, 7, 42])
def test_new_price_settles_after_delivery_and_ack(seed):
    station = "S-%d" % seed
    price = 100 + seed
    sim = nrvv_env.Simulation(seed=seed, station_ids=(station,), initial_price=None)
    sim.connect(app)

    result = sim.submit(station, price)
    assert _is_accepted(result)

    if not sim.in_flight:
        pytest.skip("precondition not reached: no send was made after submit")

    # before delivery
    st = app.get_station_state(station)
    assert _field(st, "latest_desired_price") == price
    assert _field(st, "settled") is False

    # deliver the send to the station; acknowledgement still pending
    sends = sim.in_flight
    sim.deliver(sends[0].send_id, station)
    assert sim.station_price(station) == price
    st = app.get_station_state(station)
    assert _field(st, "settled") is False

    # acknowledge
    sim.deliver_ack()
    st = app.get_station_state(station)
    assert _field(st, "latest_desired_price") == price
    assert _field(st, "last_acknowledged_price") == price
    assert _field(st, "settled") is True
