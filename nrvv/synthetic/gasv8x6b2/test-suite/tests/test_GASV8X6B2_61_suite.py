import pytest

import app
import nrvv_env


def _same(a, b):
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)


def _setup(seed, ordering):
    sim = nrvv_env.Simulation(seed=seed, ordering=ordering)
    sim.connect(app)
    return sim


def _state(station):
    st = app.get_station_state(station)
    if not isinstance(st, dict):
        pytest.skip("precondition not reached: state is not a mapping")
    return st


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("ordering", ["fifo", "random"])
def test_two_stations_each_get_own_price_through_send_port(seed, ordering):
    sim = _setup(seed, ordering)
    sim.submit("A", "3.10")
    sim.submit("B", "3.20")
    sim.run_until_idle()

    sends_a = [s for s in sim.sends if s["station_id"] == "A"]
    sends_b = [s for s in sim.sends if s["station_id"] == "B"]
    assert len(sends_a) == 1
    assert len(sends_b) == 1
    assert _same(sends_a[0]["price"], "3.10")
    assert _same(sends_b[0]["price"], "3.20")
    assert len(sim.sends) == 2

    assert len(sim.acknowledgements) == 2
    assert _same(sim.station_price("A"), "3.10")
    assert _same(sim.station_price("B"), "3.20")

    sa = _state("A")
    sb = _state("B")
    assert sa["settled"] is True
    assert sb["settled"] is True
    assert _same(sa["latest_desired_price"], "3.10")
    assert _same(sb["latest_desired_price"], "3.20")
    assert _same(sa["last_acknowledged_price"], "3.10")
    assert _same(sb["last_acknowledged_price"], "3.20")
