"""Suite for GASV3DEV3-29.

Criterion: given a station that has an associated desired price, invoking the
service's send operation for that station causes a price update to be
transmitted whose destination is that same station and whose carried price
value equals that station's desired price.

The service receives a desired price through the inbound operation
``submit-desired-price(station, price)`` and emits the update through the
outbound ``send-update(station, price)`` port.  The environment
(``nrvv_env``) observes every emission and, once delivered, records the value
each station receives.  These tests drive ``app`` exclusively through
``nrvv_env``.
"""

import app
import nrvv_env
from nrvv_env import Simulation, random_script


# --------------------------------------------------------------------------
# Construction of the server under test.
#
# The server is obtained from ``app`` with no arguments; the outbound
# ``send-update`` port is injected by the environment after construction via
# the ``send_update`` attribute (``wire_outbound=True``).  The server reads
# that attribute when it decides to emit an update.
# --------------------------------------------------------------------------

def _new_server():
    for name in ("create_server", "make_server", "build_server",
                 "new_server", "Server", "Service"):
        factory = getattr(app, name, None)
        if factory is None:
            continue
        try:
            return factory()
        except TypeError:
            continue
    raise RuntimeError("app does not expose a no-argument server constructor")


def _make_sim(seed, script):
    server = _new_server()
    return Simulation(server=server, seed=seed, script=script,
                      wire_outbound=True, port_attr="send_update")


def _sent_to(sim, station):
    return [price for (st, price) in sim.sent if st == station]


def _delivered_to(sim, station):
    return [price for (st, price) in sim.delivered if st == station]


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def test_send_emits_update_to_that_station_with_its_desired_price():
    """A single station's desired price is emitted, addressed to it."""
    station, price = "S1", 427
    sim = _make_sim(seed=0, script=[(station, price)])
    sim.run()

    # Something was sent, and it was addressed to the intended station only.
    assert sim.sent, "expected a price update to be transmitted"
    assert all(st == station for (st, _) in sim.sent), (
        "every emitted update must be addressed to the intended station")
    # The destination carries exactly the desired price.
    assert all(pr == price for pr in _sent_to(sim, station)), (
        "the carried price must equal the station's desired price")
    assert (station, price) in sim.sent


def test_received_update_destination_and_price_exact():
    """The update the station actually receives is addressed to it and
    carries exactly the desired price (verification semantics)."""
    station, price = "alpha", 613
    sim = _make_sim(seed=1, script=[(station, price)])
    sim.run()

    assert price in _delivered_to(sim, station)
    # The receiving station ends up displaying exactly that price.
    assert sim.displayed(station) == price


def test_price_value_is_carried_exactly_for_many_values_and_seeds():
    """The carried price equals the desired price exactly, no transformation,
    across a range of values and scheduler seeds."""
    for price in (0, 1, 100, 123, 500, 999, 1000, 54321):
        for seed in (0, 1, 2, 7):
            station = "station-%d-%d" % (price, seed)
            sim = _make_sim(seed=seed, script=[(station, price)])
            sim.run()
            assert sim.sent, "nothing sent for price=%r seed=%r" % (price, seed)
            for (st, pr) in sim.sent:
                assert st == station
                assert pr == price
            assert sim.displayed(station) == price


def test_each_station_gets_its_own_desired_price_no_crosstalk():
    """With several stations, each desired price is sent to its own station
    and no other, and carries exactly that station's value."""
    desired = {"A": 101, "B": 202, "C": 303, "D": 404}
    script = list(desired.items())
    for seed in (0, 3, 5, 9):
        sim = _make_sim(seed=seed, script=script)
        sim.run()
        for station, price in desired.items():
            sent = _sent_to(sim, station)
            assert sent, "no update sent to %r (seed=%r)" % (station, seed)
            assert all(pr == price for pr in sent), (
                "station %r received a foreign price" % (station,))
            assert sim.displayed(station) == price
        # No update was ever addressed to an unknown station.
        assert all(st in desired for (st, _) in sim.sent)


def test_random_single_station_last_desired_price_is_delivered():
    """Repeated desired prices for one station: the station converges to the
    latest desired price, and every emission is addressed to that station."""
    station = "only"
    for seed in (11, 12, 13):
        raw = random_script(seed=seed, stations=[station], length=6)
        script = [(station, price) for (_, price) in raw]
        last_price = script[-1][1]
        sim = _make_sim(seed=seed, script=script)
        sim.run()
        assert sim.sent
        assert all(st == station for (st, _) in sim.sent)
        assert sim.displayed(station) == last_price
