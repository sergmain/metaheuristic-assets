"""Tests for GASV3ACC2-28: suppression of redundant price updates.

Criterion: a station whose most-recently-acknowledged price already equals the
current latest desired price must receive NO further update (zero outbound
transmit calls directed at it). Conversely, when the acknowledged value differs
from the latest desired price, an update is sent -- confirming that suppression
is triggered specifically by equality of the acknowledged and latest desired
price.

Everything is driven only through nrvv_env: the server's outbound transmit port
is wired to the simulation, and the simulation submits desired prices, delivers
updates and returns acknowledgements. The observable is nrvv_env's ordered
``sent`` log -- the record of outbound transmit calls directed at each station.
"""

import app
import nrvv_env


# Several seeds per property: nrvv_env's RNG drives transport ordering, so each
# seed realizes a different interleaving of submit / deliver / ack actions.
SEEDS = tuple(range(12))


# --- wiring app to the simulation's outbound transmit port -----------------

_IFACE = ("submit_desired_price", "acknowledgement_received",
          "get_station_state")


def _has_iface(obj):
    return all(hasattr(obj, name) for name in _IFACE)


def _wire(obj, transmit):
    for name in ("set_transmit", "set_transmit_port", "bind_transmit",
                 "wire_transmit", "set_port", "configure", "wire", "connect"):
        fn = getattr(obj, name, None)
        if callable(fn):
            try:
                fn(transmit)
                return True
            except Exception:
                pass
    for attr in ("transmit", "transmit_port", "port", "send", "emit"):
        if hasattr(obj, attr):
            try:
                setattr(obj, attr, transmit)
                return True
            except Exception:
                pass
    return False


def _try_class(cls, transmit):
    for make in (
        lambda c: c(transmit),
        lambda c: c(transmit=transmit),
        lambda c: c(transmit_port=transmit),
        lambda c: c(send=transmit),
        lambda c: c(port=transmit),
        lambda c: c(emit=transmit),
        lambda c: c(on_transmit=transmit),
    ):
        try:
            server = make(cls)
        except Exception:
            continue
        if _has_iface(server):
            return server
    try:
        server = cls()
    except Exception:
        return None
    if _has_iface(server):
        _wire(server, transmit)
        return server
    return None


def _build_server(sim):
    """Construct the `app` server, wire its transmit port to `sim`, bind it."""
    transmit = sim.transmit

    for name in ("Server", "Service", "PriceServer", "PriceService",
                 "Reconciler", "ReconciliationServer", "App", "Application",
                 "Gateway"):
        cls = getattr(app, name, None)
        if isinstance(cls, type):
            server = _try_class(cls, transmit)
            if server is not None:
                sim.bind(server)
                return server

    # Fall back to any CapWords class exposed by app.
    for name in dir(app):
        if not name[:1].isupper():
            continue
        cls = getattr(app, name)
        if isinstance(cls, type):
            server = _try_class(cls, transmit)
            if server is not None:
                sim.bind(server)
                return server

    # Fall back to module-level functions on app itself.
    if _has_iface(app):
        _wire(app, transmit)
        sim.bind(app)
        return app

    raise RuntimeError("unable to construct and wire the app server")


def _sends_to(sim, station):
    """Prices of every outbound transmit call directed at `station`, in order."""
    return [price for (s, price) in sim.sent if s == station]


# --- tests -----------------------------------------------------------------

def test_no_update_when_acknowledged_equals_latest_desired():
    # The station settles at 42 (acknowledged == 42). Re-submitting the very
    # same price 42 makes the latest desired equal the acknowledged value, so
    # processing the station must send no further update: exactly one transmit
    # ever reaches it.
    for seed in SEEDS:
        sim = nrvv_env.Simulation([("S0", 42), ("S0", 42)], seed=seed)
        _build_server(sim)
        sim.run(max_steps=1000)
        assert sim.quiescent(), seed
        assert _sends_to(sim, "S0") == [42], (seed, sim.sent)
        assert sim.applied("S0") == 42, (seed,)


def test_update_sent_when_acknowledged_differs_from_latest_desired():
    # After settling at 42, a new desired price 7 differs from the acknowledged
    # value 42, so an update IS sent. Both distinct prices are transmitted,
    # exactly once each and in order.
    for seed in SEEDS:
        sim = nrvv_env.Simulation([("S0", 42), ("S0", 7)], seed=seed)
        _build_server(sim)
        sim.run(max_steps=1000)
        assert sim.quiescent(), seed
        assert _sends_to(sim, "S0") == [42, 7], (seed, sim.sent)
        assert sim.applied("S0") == 7, (seed,)


def test_repeated_identical_submissions_emit_only_once():
    # Six submissions all carrying the same price. Once the acknowledged value
    # equals the desired price, every subsequent processing is suppressed, so
    # only a single transmit occurs.
    for seed in SEEDS:
        sim = nrvv_env.Simulation([("S0", 5)] * 6, seed=seed)
        _build_server(sim)
        sim.run(max_steps=1000)
        assert sim.quiescent(), seed
        assert _sends_to(sim, "S0") == [5], (seed, sim.sent)
        assert sim.applied("S0") == 5, (seed,)


def test_suppression_is_per_station():
    # Two independent stations in one run. A re-submits an already-acknowledged
    # price (suppressed -> one send); B's second desired price differs from its
    # acknowledged value (not suppressed -> an update is sent). This shows the
    # suppression is keyed on the per-station equality of acknowledged and
    # latest desired price.
    for seed in SEEDS:
        sim = nrvv_env.Simulation(
            [("A", 10), ("B", 20), ("A", 10), ("B", 25)], seed=seed)
        _build_server(sim)
        sim.run(max_steps=1000)
        assert sim.quiescent(), seed
        assert _sends_to(sim, "A") == [10], (seed, sim.sent)
        assert _sends_to(sim, "B") == [20, 25], (seed, sim.sent)
        assert sim.applied("A") == 10, (seed,)
        assert sim.applied("B") == 25, (seed,)
