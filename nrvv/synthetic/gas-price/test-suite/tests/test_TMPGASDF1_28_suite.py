"""Suite for TMPGASDF1-28: the send-when-not-known-displayed rule.

A station is evaluated whenever its latestDesired changes or an acknowledgement
arrives. On evaluation the service sends exactly one price update carrying the
current latestDesired precisely when all hold:
  * latestDesired is set,
  * no update is outstanding, and
  * latestDesired differs from knownDisplayed (initial 'unknown' differs from
    every price).
Immediately after such a send, outstanding equals the sent price. If any
condition fails, no update is sent and outstanding is unchanged.

Everything is driven through `app` and `nrvv_env` only.
"""
import app
from nrvv_env import Simulation, DeliveryRecord, AckRecord


# --------------------------------------------------------------------------
# helpers: build a server wired to a simulation, and read its state view
# --------------------------------------------------------------------------
_MISSING = object()


def _build(seed=0, **kw):
    kw.setdefault("num_bursts", 0)          # empty script: we inject manually
    sim = Simulation(seed=seed, **kw)
    server = app.Service(sim.send_update)
    sim.connect(server)
    return sim, server


def _lookup(view, names):
    for n in names:
        if isinstance(view, dict):
            if n in view:
                return view[n]
        elif hasattr(view, n):
            return getattr(view, n)
    return _MISSING


def _outstanding(server, station):
    v = _lookup(server.inspect(station),
                ["outstanding", "outstanding_price", "outstandingPrice",
                 "outstanding_price_or_none"])
    assert v is not _MISSING, "inspect() must expose the outstanding price-or-none"
    return v


def _known(server, station):
    return _lookup(server.inspect(station),
                   ["known_displayed", "knownDisplayed", "known", "displayed"])


def _latest(server, station):
    return _lookup(server.inspect(station),
                   ["latest_desired", "latestDesired", "latest", "desired"])


def _sends_for(sim, station):
    return [r for r in sim.send_log if r.station == station]


def _step_delivery(sim):
    rec = sim.step()
    assert isinstance(rec, DeliveryRecord), "expected a delivery event, got %r" % (rec,)
    return rec


def _step_ack(sim):
    rec = sim.step()
    assert isinstance(rec, AckRecord), "expected an acknowledgement event, got %r" % (rec,)
    return rec


# --------------------------------------------------------------------------
# tests
# --------------------------------------------------------------------------
def test_first_set_sends_and_sets_outstanding():
    # knownDisplayed is 'unknown', which differs from every price, so the very
    # first desired price must be sent and become outstanding.
    sim, server = _build()
    sim.inject_desired("S0", 5)

    sends = _sends_for(sim, "S0")
    assert len(sends) == 1
    assert sends[0].price == 5
    assert _outstanding(server, "S0") == 5
    assert _latest(server, "S0") == 5


def test_outstanding_blocks_further_send():
    # With an update already outstanding, a new desired price must not be sent
    # and outstanding must be unchanged.
    sim, server = _build()
    sim.inject_desired("S0", 5)
    assert len(_sends_for(sim, "S0")) == 1
    assert _outstanding(server, "S0") == 5

    sim.inject_desired("S0", 8)          # outstanding -> no send

    assert len(_sends_for(sim, "S0")) == 1
    assert _outstanding(server, "S0") == 5
    assert _latest(server, "S0") == 8    # recorded, but not yet sent


def test_delivery_alone_does_not_trigger_send():
    # Evaluation happens only on a desired-price change or an ack; mere delivery
    # of an update to the station is neither, so nothing new is sent.
    sim, server = _build()
    sim.inject_desired("S0", 5)
    assert len(_sends_for(sim, "S0")) == 1

    _step_delivery(sim)                  # station now shows 5, but no ack yet

    assert len(_sends_for(sim, "S0")) == 1
    assert _outstanding(server, "S0") == 5


def test_equal_to_known_displayed_no_send():
    # After convergence at 5, setting the same value again (equal to
    # knownDisplayed) must send nothing and leave outstanding empty.
    sim, server = _build()
    sim.inject_desired("S0", 5)
    _step_delivery(sim)
    _step_ack(sim)                       # knownDisplayed := 5, outstanding cleared

    assert len(_sends_for(sim, "S0")) == 1
    assert _outstanding(server, "S0") is None
    assert _known(server, "S0") == 5

    sim.inject_desired("S0", 5)          # equals knownDisplayed -> no send

    assert len(_sends_for(sim, "S0")) == 1
    assert _outstanding(server, "S0") is None


def test_differing_after_convergence_sends_again():
    # After convergence at 5, a new, different desired price must be sent and
    # become outstanding.
    sim, server = _build()
    sim.inject_desired("S0", 5)
    _step_delivery(sim)
    _step_ack(sim)
    assert len(_sends_for(sim, "S0")) == 1

    sim.inject_desired("S0", 9)          # differs from knownDisplayed -> send

    sends = _sends_for(sim, "S0")
    assert len(sends) == 2
    assert sends[-1].price == 9
    assert _outstanding(server, "S0") == 9


def test_ack_triggers_send_of_latest_coalesced_value():
    # Several sets during an outstanding update coalesce; when the ack arrives
    # and clears outstanding, exactly one update carrying the *current* latest
    # desired is sent.
    sim, server = _build()
    sim.inject_desired("S0", 5)          # sent, outstanding := 5
    sim.inject_desired("S0", 8)          # blocked, latest := 8
    assert len(_sends_for(sim, "S0")) == 1
    assert _outstanding(server, "S0") == 5

    _step_delivery(sim)
    _step_ack(sim)                       # clears outstanding, re-evaluates -> send 8

    sends = _sends_for(sim, "S0")
    assert len(sends) == 2
    assert sends[-1].price == 8
    assert _outstanding(server, "S0") == 8
    assert _known(server, "S0") == 5     # ack set known to the acked price


def test_ack_with_latest_equal_known_sends_nothing_more():
    # When the ack makes knownDisplayed equal to the (unchanged) latestDesired,
    # the re-evaluation sends nothing further and leaves outstanding empty.
    sim, server = _build()
    sim.inject_desired("S0", 5)
    _step_delivery(sim)
    _step_ack(sim)                       # known := 5, latest == 5 -> no new send

    assert len(_sends_for(sim, "S0")) == 1
    assert _outstanding(server, "S0") is None
    assert _known(server, "S0") == 5


def test_no_input_no_send():
    # Never set and never evaluated: nothing is ever sent, nothing outstanding.
    sim, server = _build()
    assert sim.run() == 0
    assert sim.send_log == []
    assert _outstanding(server, "S0") is None


def test_seeded_runs_converge_under_the_rule():
    # Reliable transport + the send-when-differing rule imply that at quiescence
    # nothing is outstanding and knownDisplayed equals latestDesired for every
    # station that ever received a desired price (otherwise a send would be due
    # and the run would not be quiescent).
    for seed in (0, 1, 7, 42, 1234):
        sim = Simulation(seed=seed)
        server = app.Service(sim.send_update)
        sim.connect(server)
        sim.run()

        assert sim.is_quiescent()
        touched = {rec.station for rec in sim.input_log}
        for station in touched:
            assert _outstanding(server, station) is None, (seed, station)
            assert _known(server, station) == _latest(server, station), (seed, station)
            assert sim.displayed(station) == _known(server, station), (seed, station)
