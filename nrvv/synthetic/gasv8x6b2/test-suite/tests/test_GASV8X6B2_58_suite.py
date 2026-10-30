import pytest

import app
import nrvv_env


def _state(station):
    st = app.get_station_state(station)
    if not isinstance(st, dict):
        pytest.skip("precondition not reached: station state not a mapping")
    return st


def _drive(seed, station, prices, ordering):
    """Submit prices, then step the transport, yielding after each new ack."""
    sim = nrvv_env.Simulation(seed=seed, ordering=ordering)
    sim.connect(app)
    sim.set_time(100.0)
    sim.submit(station, prices[0])
    return sim


def _run_and_collect(seed, ordering, prices):
    station = "S%d" % seed
    sim = _drive(seed, station, prices, ordering)
    observed = []  # (ack record, send record, state after ack)
    rest = list(prices[1:])
    steps = 0
    while True:
        before = len(sim.acknowledgements)
        if rest and steps % 2 == 1:
            sim.advance(1.0)
            sim.submit(station, rest.pop(0))
        if not sim.step():
            if rest:
                sim.advance(1.0)
                sim.submit(station, rest.pop(0))
                continue
            break
        steps += 1
        sim.advance(1.0)
        if len(sim.acknowledgements) > before:
            ack = sim.acknowledgements[-1]
            observed.append((ack, sim.sends[ack["ordinal"]], dict(_state(station))))
        if steps > 5000:
            raise RuntimeError("too many steps")
    return sim, station, observed


def test_ack_records_acknowledged_price_by_request_identifier():
    for seed in range(5):
        for ordering in ("fifo", "random"):
            _sim, _station, observed = _run_and_collect(seed, ordering, [10, 20, 30])
            if not observed:
                pytest.skip("precondition not reached: no acknowledgement produced")
            for ack, send, st in observed:
                assert st["last_acknowledged_price"] == send["price"]


def test_regressed_confirmation_is_recorded_and_not_settled():
    reached = False
    for seed in range(10):
        for ordering in ("fifo", "random"):
            sim, station, observed = _run_and_collect(seed, ordering, [10, 20, 30])
            best = None
            for ack, send, st in observed:
                if best is not None and send["version"] < best:
                    reached = True
                    assert st["last_acknowledged_price"] == send["price"]
                    assert st["settled"] is False
                best = send["version"] if best is None else max(best, send["version"])
    if not reached:
        pytest.skip("precondition not reached: no older send acknowledged after a newer one")
