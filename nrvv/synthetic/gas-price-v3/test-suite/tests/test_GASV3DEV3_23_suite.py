"""Suite for TEST_CASE GASV3DEV3-23 (requirement GASV3DEV3-4).

Criterion: with an earlier update to a station still unacknowledged (in flight),
supplying two or more new desired prices in sequence for that station must:
  * transmit none of those newly arrived prices while the update stays
    unacknowledged,
  * retain as the station's pending price the value of the LAST-arrived price
    (and not any earlier one),
  * and, once the station becomes free, send exactly one update carrying that
    most-recent price while every superseded intermediate price is discarded
    and never transmitted.

Every test drives ``app`` only through ``nrvv_env``.
"""

import inspect as _inspect

import app
from nrvv_env import Simulation


# --------------------------------------------------------------------------
# Server construction / wiring helpers.
#
# The Interface only promises that every operation is a snake_case function or
# method of ``app``.  It does not say whether the server is the module itself,
# a class instance, or produced by a factory.  These helpers locate the server
# object in a way that works for any of those shapes, and wire the outbound
# ``send-update`` port through the simulation.
# --------------------------------------------------------------------------

_OPS = ("submit_desired_price", "acknowledge", "inspect_station")


def _has_ops(obj):
    return all(callable(getattr(obj, m, None)) for m in _OPS)


def _find_server_class(mod):
    for name in dir(mod):
        obj = getattr(mod, name)
        if _inspect.isclass(obj) and all(hasattr(obj, m) for m in _OPS):
            return obj
    return None


def _instantiate(cls, port):
    for attempt in (
        lambda: cls(port),
        lambda: cls(send_update=port),
        lambda: cls(outbound=port),
        lambda: cls(send_update_port=port),
        lambda: cls(),
    ):
        try:
            obj = attempt()
        except TypeError:
            continue
        except Exception:
            continue
        if _has_ops(obj):
            return obj
    return cls()


def _make_server(mod, port):
    # 1) The module itself exposes the operations.
    if _has_ops(mod):
        return mod
    # 2) A class whose instances expose the operations.
    cls = _find_server_class(mod)
    if cls is not None:
        return _instantiate(cls, port)
    # 3) A factory producing a server object.
    for fname in ("create_server", "make_server", "new_server", "build_server",
                  "create", "server", "service", "Service", "Server", "App"):
        f = getattr(mod, fname, None)
        if callable(f):
            for attempt in (lambda f=f: f(port),
                            lambda f=f: f(send_update=port),
                            lambda f=f: f()):
                try:
                    obj = attempt()
                except TypeError:
                    continue
                except Exception:
                    continue
                if _has_ops(obj):
                    return obj
    raise RuntimeError("cannot locate the server object within `app`")


def build(seed):
    """Create a fresh simulation wired to a fresh server for the given seed."""
    sim = Simulation(seed=seed)
    server = _make_server(app, sim.outbound)
    # Wire the outbound port (harmless if the server was already injected).
    sim.attach(server, wire_outbound=True)
    return sim, server


# --------------------------------------------------------------------------
# Inspection helper.
#
# The query ``inspect-station`` returns the displayed value, whether an update
# is outstanding (and its sent price), and the pending price.  The exact
# container shape is not specified, so we flatten whatever it returns into the
# set of scalar values it contains.  By choosing all prices distinct, we can
# assert a given price value is present (retained) or absent (discarded)
# without depending on field names or layout.
# --------------------------------------------------------------------------

def _scalars(obj):
    out = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif hasattr(o, "_asdict") and callable(getattr(o, "_asdict")):
            walk(o._asdict())
        elif isinstance(o, (list, tuple, set, frozenset)):
            for v in o:
                walk(v)
        elif hasattr(o, "__dict__") and vars(o):
            walk(vars(o))
        else:
            out.append(o)

    walk(obj)
    return out


# --------------------------------------------------------------------------
# Tests.
# --------------------------------------------------------------------------

def test_coalesced_pending_retains_last_and_is_sent_once_when_free():
    """Two-plus prices arriving in flight: none sent now; last retained; one
    update with the latest price sent once the station is free."""
    for seed in (0, 1, 7, 42):
        sim, server = build(seed)
        station = "station-A"
        p0, p1, p2, p3 = 100, 200, 300, 400  # all distinct

        # Station is free: first submission produces exactly one send-update.
        server.submit_desired_price(station, p0)
        assert sim.sent == [(station, p0)]
        assert len(sim.pending_updates()) == 1

        # While that update is in flight (unacknowledged), supply new prices.
        server.submit_desired_price(station, p1)
        server.submit_desired_price(station, p2)
        server.submit_desired_price(station, p3)

        # None of the newly arrived prices is transmitted while in flight.
        assert sim.sent == [(station, p0)]
        assert len(sim.pending_updates()) == 1

        # The retained pending price is the last-arrived one; the intermediate
        # prices have been discarded and are not retained anywhere.
        vals = _scalars(sim.inspect(station))
        assert p3 in vals
        assert p1 not in vals
        assert p2 not in vals

        # Let the outstanding update be delivered and acknowledged.
        u = sim.pending_updates()[0]
        assert u.price == p0
        sim.deliver(u.seq)
        sim.deliver_ack()

        # Now free: exactly one new update, carrying the most-recent price.
        assert sim.sent == [(station, p0), (station, p3)]
        assert (station, p1) not in sim.sent
        assert (station, p2) not in sim.sent

        # Drive to quiescence: convergence to the latest value, nothing else.
        sim.run()
        assert sim.sent == [(station, p0), (station, p3)]
        assert sim.displayed(station) == p3
        tail = _scalars(sim.inspect(station))
        assert p1 not in tail
        assert p2 not in tail


def test_many_coalesced_prices_only_the_most_recent_transmitted():
    """With more than two new prices arriving in flight, only the final one is
    ever transmitted; all superseded intermediates are discarded."""
    for seed in (2, 13, 99):
        sim, server = build(seed)
        station = "S1"
        first = 500
        burst = [510, 520, 530, 540, 550]  # last is 550

        server.submit_desired_price(station, first)
        assert sim.sent == [(station, first)]

        for p in burst:
            server.submit_desired_price(station, p)
            # Nothing new transmitted while the first update is unacknowledged.
            assert sim.sent == [(station, first)]
            assert len(sim.pending_updates()) == 1

        # Only the last-arrived price is retained as pending.
        vals = _scalars(sim.inspect(station))
        assert burst[-1] in vals
        for p in burst[:-1]:
            assert p not in vals

        # Free the station by delivering and acknowledging the outstanding one.
        u = sim.pending_updates()[0]
        sim.deliver(u.seq)
        sim.deliver_ack()

        # Exactly one further update, carrying the most recent price.
        assert sim.sent == [(station, first), (station, burst[-1])]
        for p in burst[:-1]:
            assert (station, p) not in sim.sent

        sim.run()
        assert sim.displayed(station) == burst[-1]
        assert sim.sent == [(station, first), (station, burst[-1])]


def test_pending_price_is_last_arrived_not_an_earlier_one():
    """Ordering matters: the pending value tracks the most recently arrived
    price even as successive prices overwrite it while in flight."""
    for seed in (5, 21):
        sim, server = build(seed)
        station = "alpha"

        server.submit_desired_price(station, 10)  # free -> sent once
        assert sim.sent == [(station, 10)]

        # Successive arrivals while in flight; pending should follow the newest.
        for latest in (20, 30, 40):
            server.submit_desired_price(station, latest)
            assert sim.sent == [(station, 10)]  # still nothing new sent
            vals = _scalars(sim.inspect(station))
            assert latest in vals  # pending equals the latest arrival

        # Earlier superseded arrivals are no longer retained.
        vals = _scalars(sim.inspect(station))
        assert 20 not in vals
        assert 30 not in vals
        assert 40 in vals

        u = sim.pending_updates()[0]
        sim.deliver(u.seq)
        sim.deliver_ack()

        # One update sent, carrying the final value; no intermediate sent.
        assert sim.sent == [(station, 10), (station, 40)]
        assert (station, 20) not in sim.sent
        assert (station, 30) not in sim.sent

        sim.run()
        assert sim.displayed(station) == 40
        assert sim.sent == [(station, 10), (station, 40)]
