"""Test suite for GASV3DEV3-28 / requirement GASV3DEV3-2.

Criterion: drive the service with a sequence of desired prices for a station,
stop submitting, and let every update the service sent become acknowledged.
Once the station is quiescent and fully acknowledged, the value it *displays*
must equal the latest desired price supplied for it (not any earlier/other
price).

Every test drives `app` only through `nrvv_env`.  The simulation's
``displayed(station)`` is the authoritative value a passive station shows (it
is set each time an update is delivered), so it is exactly "the value the
station displays" that the criterion talks about.
"""

import importlib

import app
import nrvv_env


# --------------------------------------------------------------------------
# Locating and wiring the server through the `app` Python binding.
# --------------------------------------------------------------------------

_IFACE = ("submit_desired_price", "acknowledge", "inspect_station")


def _find_server_class(mod):
    """Return the CapWords class of ``app`` implementing the inbound Interface."""
    cands = []
    for name in dir(mod):
        try:
            obj = getattr(mod, name)
        except Exception:
            continue
        if isinstance(obj, type) and all(
            callable(getattr(obj, m, None)) for m in _IFACE
        ):
            cands.append(obj)
    cands.sort(
        key=lambda c: 0
        if getattr(c, "__module__", "") == getattr(mod, "__name__", "app")
        else 1
    )
    return cands[0] if cands else None


def _build(sim):
    """Create a fresh server, wire its outbound send-update port and attach it."""
    mod = app
    cls = _find_server_class(mod)
    if cls is not None:
        server = None
        for maker in (
            lambda: cls(sim.outbound),
            lambda: cls(send_update=sim.outbound),
            lambda: cls(outbound=sim.outbound),
            lambda: cls(),
        ):
            try:
                server = maker()
                break
            except TypeError:
                continue
        if server is None:
            server = cls()
        # Also expose the port as an attribute (harmless if constructor took it).
        sim.attach(server, wire_outbound=True)
        return server

    # Fallback: the operations are module-level functions of `app`.  Reload to
    # reset any global state so each test is independent.
    mod = importlib.reload(app)
    if all(callable(getattr(mod, m, None)) for m in _IFACE):
        sim.attach(mod, wire_outbound=True)
        return mod

    raise RuntimeError("could not locate the app server interface")


# --------------------------------------------------------------------------
# Deterministic helpers.
# --------------------------------------------------------------------------

def _last_desired(script):
    """Map each station to the last desired price submitted for it."""
    last = {}
    for station, price in script:
        last[station] = price
    return last


def _drain(sim):
    """Acknowledge every sent update until nothing is in flight.

    After all submissions have been fired, repeatedly deliver every in-flight
    update and then every in-flight acknowledgement.  Delivering an ack may
    cause the server to emit the station's pending update, which the next
    outer iteration picks up; the loop ends only when the server stops
    emitting (fully acknowledged, quiescent).
    """
    guard = 0
    while sim.in_flight():
        guard += 1
        assert guard < 100000, "drain did not converge"
        for u in sim.pending_updates():
            sim.deliver(u.seq)
        while sim.pending_acks():
            sim.deliver_ack()


# --------------------------------------------------------------------------
# Tests.
# --------------------------------------------------------------------------

def test_single_station_handdriven_displays_latest():
    """Submit a sequence, stop, ack everything by hand: display == last price."""
    script = [("S1", 100), ("S1", 200), ("S1", 150), ("S1", 420)]
    sim = nrvv_env.Simulation(seed=0, script=list(script))
    _build(sim)

    # Drive the whole sequence of desired prices, then stop submitting.
    while sim.pending_submissions:
        sim.fire_submission()

    # Let every update the service sent become acknowledged.
    _drain(sim)

    assert sim.quiescent()
    assert sim.displayed("S1") == 420


def test_single_station_seeded_run_displays_latest():
    """Across several schedulings the converged display is the latest price."""
    prices = [300, 450, 275, 600, 125, 999]
    script = [("ST", p) for p in prices]
    for seed in range(6):
        sim = nrvv_env.Simulation(seed=seed, script=list(script))
        _build(sim)
        sim.run()
        assert sim.quiescent()
        assert sim.displayed("ST") == prices[-1]


def test_bursts_before_any_ack_display_latest():
    """A burst of submissions (earlier ones still unacked) converges to last."""
    prices = [10, 20, 30, 40, 50]
    script = [("B", p) for p in prices]
    for seed in range(5):
        sim = nrvv_env.Simulation(seed=100 + seed, script=list(script))
        _build(sim)
        sim.run()
        assert sim.quiescent()
        # The display must be the latest, never an earlier burst value.
        assert sim.displayed("B") == 50


def test_multi_station_random_scripts_each_converges():
    """Each station converges to its own latest desired price, independently."""
    stations = ["A", "B", "C", "D"]
    for seed in range(8):
        script = nrvv_env.random_script(seed, stations, length=40)
        last = _last_desired(script)
        sim = nrvv_env.Simulation(seed=seed * 7 + 1, script=script)
        _build(sim)
        sim.run()
        assert sim.quiescent()
        for st in stations:
            if st in last:
                assert sim.displayed(st) == last[st]


def test_multi_station_handdriven_each_converges():
    """Hand-driven drain across stations: each display == its latest price."""
    script = [
        ("X", 111), ("Y", 222), ("X", 333),
        ("Z", 444), ("Y", 555), ("X", 666),
        ("Z", 777), ("Y", 888),
    ]
    last = _last_desired(script)
    sim = nrvv_env.Simulation(seed=3, script=list(script))
    _build(sim)

    while sim.pending_submissions:
        sim.fire_submission()
    _drain(sim)

    assert sim.quiescent()
    for st, price in last.items():
        assert sim.displayed(st) == price
