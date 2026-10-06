"""Suite for TMPGASDF1-29 / requirement TMPGASDF1-10.

Liveness: with ``latestDesired`` fixed and no newer desired price set thereafter,
every outstanding update is eventually acknowledged, each acknowledgement sets
``knownDisplayed`` and re-evaluates, and within finitely many send/acknowledge
cycles the station converges so that ``knownDisplayed == latestDesired``, the
station displays ``latestDesired``, the send condition is false (nothing more is
sent), and it remains stably displaying ``latestDesired``.

Everything is driven through ``nrvv_env`` only; ``num_bursts=0`` disables the
seeded price-source script so the test fully controls which desired prices are
set and guarantees no newer desired price is injected thereafter.
"""
import app
from nrvv_env import Simulation


# ---------------------------------------------------------------------------
# Helpers to read the service's own view from inspect(station) robustly,
# without assuming an exact key/field spelling for the returned structure
# ({latest-desired, known-displayed, outstanding-price-or-none}).
# ---------------------------------------------------------------------------
def _field(view, idx, *names):
    if isinstance(view, dict):
        for n in names:
            if n in view:
                return view[n]
        norm = {str(k).replace('-', '_').lower(): v for k, v in view.items()}
        for n in names:
            if n in norm:
                return norm[n]
        raise AssertionError("cannot extract %r from %r" % (names, view))
    if isinstance(view, (tuple, list)):
        return view[idx]
    for n in names:
        if hasattr(view, n):
            return getattr(view, n)
    raise AssertionError("cannot extract %r from %r" % (names, view))


def _latest_desired(view):
    return _field(view, 0, 'latest_desired', 'latestdesired', 'latest')


def _known_displayed(view):
    return _field(view, 1, 'known_displayed', 'knowndisplayed', 'known')


def _outstanding(view):
    return _field(view, 2, 'outstanding', 'outstanding_price',
                  'outstanding_price_or_none', 'outstanding_or_none', 'pending')


def _new_sim(seed):
    """A simulation with the seeded script disabled, server wired in."""
    sim = Simulation(seed=seed, num_bursts=0)
    server = app.Service(sim.send_update)
    sim.connect(server)
    return sim, server


def _assert_converged(sim, server, station, value):
    """Full convergence + quiescence check for one station at ``value``."""
    assert sim.is_quiescent(), "simulation should be quiescent after run()"
    view = server.inspect(station)
    assert _latest_desired(view) == value
    # knownDisplayed equals latestDesired (the service believes it converged)
    assert _known_displayed(view) == value
    # nothing outstanding: the send condition is settled
    assert _outstanding(view) in (None, value) and (
        _outstanding(view) is None), "nothing should be outstanding"
    # the station actually displays latestDesired
    assert sim.displayed(station) == value


def _assert_stable(sim, server, station, value):
    """Re-driving/re-evaluating must not send again nor change the display."""
    sends_before = len(sim.send_log)
    # Re-evaluate explicitly by re-asserting the SAME desired (no newer value):
    sim.inject_desired(station, value)
    extra = sim.run()
    assert extra == 0, "converged station must not schedule further events"
    assert len(sim.send_log) == sends_before, "send condition must be false"
    assert sim.displayed(station) == value
    view = server.inspect(station)
    assert _known_displayed(view) == value
    assert _outstanding(view) is None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_single_fixed_desired_converges_and_is_stable():
    sim, server = _new_sim(seed=1)
    sim.inject_desired('S0', 7)
    sim.run()
    _assert_converged(sim, server, 'S0', 7)
    _assert_stable(sim, server, 'S0', 7)


def test_coalesced_burst_converges_to_latest_desired_in_cycles():
    # Two desired prices land in quick succession on one station while the
    # first update is still outstanding, so the second coalesces and is only
    # sent after the first is acknowledged: more than one send/ack cycle.
    sim, server = _new_sim(seed=3)
    sim.inject_desired('S0', 5)     # sent immediately -> outstanding
    sim.inject_desired('S0', 12)    # latestDesired, coalesced while outstanding
    sim.run()

    sends_s0 = [r for r in sim.send_log if r.station == 'S0']
    # finitely many cycles, and strictly more than one (a real convergence run)
    assert len(sends_s0) >= 2
    assert sends_s0[-1].price == 12          # the last update carried latestDesired
    # update-identifiers are monotonically increasing per station (TMPGASDF1-12)
    ids = [r.update_id for r in sends_s0]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)

    _assert_converged(sim, server, 'S0', 12)
    _assert_stable(sim, server, 'S0', 12)


def test_each_acknowledgement_sets_known_displayed_to_acked_price():
    # Drive step by step and confirm every acknowledgement sets knownDisplayed
    # to that update's price and that the final ack settles it at latestDesired.
    sim, server = _new_sim(seed=9)
    sim.inject_desired('S0', 4)
    sim.inject_desired('S0', 15)    # latestDesired

    acked_prices = []
    guard = 0
    while not sim.is_quiescent():
        guard += 1
        assert guard < 1000, "must converge in finitely many cycles"
        ev = sim.step()
        if ev is None:
            break
        if ev in sim.ack_log and ev is sim.ack_log[-1]:
            # an acknowledgement was just fed back; knownDisplayed must reflect it
            view = server.inspect('S0')
            assert _known_displayed(view) == ev.price
            acked_prices.append(ev.price)

    assert acked_prices, "at least one acknowledgement must occur"
    assert acked_prices[-1] == 15            # convergence settles at latestDesired
    _assert_converged(sim, server, 'S0', 15)


def test_convergence_under_reordering_across_seeds():
    # Several stations, each a single fixed desired price set once; the seeded
    # scheduler may reorder deliveries across stations. Every station must still
    # converge to its own latestDesired and stay there.
    values = {'S0': 3, 'S1': 11, 'S2': 18, 'S3': 6}
    for seed in (1, 2, 7, 42, 123):
        sim, server = _new_sim(seed=seed)
        for sid, price in values.items():
            sim.inject_desired(sid, price)
        sim.run()
        for sid, price in values.items():
            _assert_converged(sim, server, sid, price)
        # quiescent and no further sends happen on an extra drive
        sends_before = len(sim.send_log)
        assert sim.run() == 0
        assert len(sim.send_log) == sends_before


def test_no_further_update_sent_once_displayed():
    # After convergence the send condition is false: re-asserting the already
    # displayed value (no newer desired) emits nothing and keeps the display.
    sim, server = _new_sim(seed=50)
    sim.inject_desired('S2', 14)
    sim.run()
    _assert_converged(sim, server, 'S2', 14)

    sends_before = len(sim.send_log)
    for _ in range(3):
        sim.inject_desired('S2', 14)
        assert sim.run() == 0
    assert len(sim.send_log) == sends_before
    assert sim.displayed('S2') == 14
    view = server.inspect('S2')
    assert _known_displayed(view) == 14
    assert _outstanding(view) is None
