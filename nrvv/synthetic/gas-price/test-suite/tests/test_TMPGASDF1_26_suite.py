"""Suite for TMPGASDF1-26 (requirement TMPGASDF1-2).

Criterion: after the latest desired price for a station has been set and no newer
desired price for that station is set afterward, within a finite elapsed time the
station's displayed price becomes equal to that latest desired price and remains
equal to it. It must not fail to reach that value nor settle on any other value.

Every test drives `app` only through `nrvv_env`. The authoritative "displayed
price" is the environment's station display, read via ``sim.displayed(station)``.
``server.inspect`` is used only tolerantly, as an extra confirmation.
"""
import app
from nrvv_env import Simulation

# Several seeds per property: convergence must hold regardless of the seeded
# scheduler's reordering / coalescing choices.
SEEDS = [0, 1, 2, 3, 7, 42, 1234]

_MISSING = object()


def _build(seed, **kw):
    """Construct a server wired to a fresh seeded simulation."""
    sim = Simulation(seed, **kw)
    server = app.Service(sim.send_update)
    sim.connect(server)
    return sim, server


def _lookup(view, names):
    for n in names:
        if isinstance(view, dict) and n in view:
            return view[n]
    for n in names:
        if hasattr(view, n):
            return getattr(view, n)
    return _MISSING


def _view_fields(view):
    """Best-effort extraction of (latest_desired, known_displayed, outstanding)."""
    latest = _lookup(view, ("latest_desired", "latest-desired", "latest"))
    displayed = _lookup(view, ("known_displayed", "known-displayed", "displayed"))
    outstanding = _lookup(
        view,
        ("outstanding", "outstanding_price", "outstanding_price_or_none",
         "outstanding-price-or-none"),
    )
    return latest, displayed, outstanding


def test_single_desired_price_becomes_displayed():
    # Set exactly one desired price and never set a newer one; the station must
    # end up displaying precisely that value.
    for seed in SEEDS:
        sim, _ = _build(seed, num_bursts=0)
        price = 13
        sim.inject_desired("S0", price)
        steps = sim.run()  # finite: run() raises if quiescence is never reached
        assert steps >= 0
        assert sim.is_quiescent()
        assert sim.displayed("S0") == price


def test_displayed_price_remains_equal_after_convergence():
    # Once converged and with no newer desired price set, the displayed price
    # must stay equal to the latest desired value.
    for seed in SEEDS:
        sim, _ = _build(seed, num_bursts=0)
        price = 6
        sim.inject_desired("S1", price)
        sim.run()
        assert sim.displayed("S1") == price
        # No further desired price is set; the system must stay settled.
        extra = sim.run()
        assert extra == 0
        assert sim.is_quiescent()
        assert sim.displayed("S1") == price


def test_latest_of_a_burst_is_the_displayed_value():
    # Several desired prices set in quick succession for one station: the station
    # must converge on the LAST one, not on any earlier (superseded) value.
    sequence = (3, 9, 17, 5)
    for seed in SEEDS:
        sim, _ = _build(seed, num_bursts=0)
        for p in sequence:
            sim.inject_desired("S2", p)
        sim.run()
        assert sim.is_quiescent()
        assert sim.displayed("S2") == sequence[-1]


def test_converges_to_final_after_seeded_script():
    # Let the full seeded script run to quiescence, then set one final desired
    # price for a station and set nothing newer: it must converge to that value.
    for seed in SEEDS:
        sim, _ = _build(seed)  # default seeded script of bursts
        sim.run()              # drain the script (no newer prices remain)
        final = 11
        sim.inject_desired("S3", final)
        sim.run()
        assert sim.is_quiescent()
        assert sim.displayed("S3") == final


def test_every_station_displays_its_own_latest_desired():
    # After draining the script, give each station a distinct final desired price
    # (interleaved); each must converge to its own latest value.
    for seed in SEEDS:
        sim, _ = _build(seed)
        sim.run()
        finals = {"S0": 2, "S1": 8, "S2": 14, "S3": 19}
        for sid, p in finals.items():
            sim.inject_desired(sid, p)
        sim.run()
        assert sim.is_quiescent()
        for sid, p in finals.items():
            assert sim.displayed(sid) == p


def test_service_view_confirms_convergence():
    # The service's own read-only view must agree with the displayed price and
    # report nothing outstanding once converged.
    for seed in SEEDS:
        sim, server = _build(seed, num_bursts=0)
        price = 7
        sim.inject_desired("S0", price)
        sim.run()
        assert sim.is_quiescent()
        assert sim.displayed("S0") == price  # authoritative, non-vacuous check
        latest, known_displayed, outstanding = _view_fields(server.inspect("S0"))
        if latest is not _MISSING:
            assert latest == price
        if known_displayed is not _MISSING:
            assert known_displayed == price
        if outstanding is not _MISSING:
            assert outstanding is None
