"""Tests for GASV4ACCJ-12: the held price changes only on acknowledgement of a send.

Driven only through nrvv_env: the simulation makes the price changes, the server's
sends and the acknowledgements, and the held price is read with query_station_status.
"""

import importlib

import app
from nrvv_env import Simulation
from nrvv_env.simulation import SendRecord

STATION = "S1"
SEEDS = (1, 2, 3, 4, 5)
MAX_EVENTS = 100000


def _fresh_app():
    return importlib.reload(app)


def _held_price(sim, station):
    status = sim.status(station)
    if isinstance(status, dict):
        return status["held_price"]
    return status.held_price


def _step_until_send(sim):
    """Step until the first non-dropped send to STATION.

    Returns (send, held price just before that send was made). Earlier S1 sends were
    all dropped, so no S1 acknowledgement can have arrived before this send.
    """
    for _ in range(MAX_EVENTS):
        before = _held_price(sim, STATION)
        count = len(sim.sends())
        if not sim.step():
            raise AssertionError("simulation ended without a send to " + STATION)
        new = [r for r in sim.sends()[count:]
               if r.station == STATION and r.state != "dropped"]
        if new:
            return new[0], before
    raise AssertionError("no send to " + STATION + " within the event limit")


def _step_until_acked(sim, send, before):
    """Step until send is acknowledged; the held price must equal before until then."""
    for _ in range(MAX_EVENTS):
        if send.state == "acked":
            return
        if not sim.step():
            raise AssertionError("simulation ended before the acknowledgement arrived")
        if send.state != "acked":
            assert _held_price(sim, STATION) == before
    raise AssertionError("acknowledgement not delivered within the event limit")


def _unknown_send_id(sim):
    known = [r.send_id for r in sim.sends()]
    if all(isinstance(i, int) for i in known):
        return max(known, default=0) + 1000
    return "no-such-send"


def test_held_price_changes_only_on_acknowledgement_of_send():
    for seed in SEEDS:
        server = _fresh_app()
        sim = Simulation(seed)
        sim.connect(server)

        send, before = _step_until_send(sim)
        assert _held_price(sim, STATION) == before

        _step_until_acked(sim, send, before)
        assert _held_price(sim, STATION) == send.price


def test_repeated_or_unknown_acknowledgement_leaves_held_price_unchanged():
    for seed in SEEDS:
        server = _fresh_app()
        sim = Simulation(seed)
        sim.connect(server)

        send, before = _step_until_send(sim)
        _step_until_acked(sim, send, before)
        assert _held_price(sim, STATION) == send.price

        # Second acknowledgement carrying the same send identifier A.
        repeat = SendRecord(send.index, send.station, send.send_id, send.price, send.sent_at)
        sim._do_ack(repeat)
        assert _held_price(sim, STATION) == send.price

        # Acknowledgement carrying a send identifier with no outstanding send.
        unknown = SendRecord(-1, STATION, _unknown_send_id(sim), send.price, sim.now)
        sim._do_ack(unknown)
        assert _held_price(sim, STATION) == send.price
