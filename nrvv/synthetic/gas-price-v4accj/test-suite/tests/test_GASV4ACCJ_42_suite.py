"""Checks GASV4ACCJ-15: an outstanding send that is not acknowledged is abandoned after 30 seconds."""

import importlib

import pytest

import app
from nrvv_env import Simulation

ABANDON_AFTER = 30.0
CASES = 3
SEEDS = range(1, 300)


def _fresh_app():
    # Each case starts from a freshly loaded app, so no state carries over between cases.
    return importlib.reload(app)


def _field(obj, *names):
    for name in names:
        if isinstance(obj, dict):
            if name in obj:
                return obj[name]
        elif hasattr(obj, name):
            return getattr(obj, name)
    raise AssertionError(f"status has none of {names}: {obj!r}")


def _held(status):
    return _field(status, "held_price", "held")


def _desired(status):
    return _field(status, "desired_price", "desired")


def _outstanding_price(status):
    send = _field(status, "outstanding_send", "outstanding")
    if send is None:
        return None
    if isinstance(send, (int, float)):
        return send
    return _field(send, "price")


def _sends_started_between(sim, record, start, end):
    return [r for r in sim.sends()
            if r.index > record.index and r.station == record.station
            and start <= r.sent_at < end]


def _withheld_cases(count):
    """Yield (sim, record) for the first `count` seeds whose send is dropped, so it is never acknowledged."""
    found = 0
    for seed in SEEDS:
        app_module = _fresh_app()
        sim = Simulation(seed)
        sim.connect(app_module)
        seen = 0
        record = None
        while record is None and sim.step():
            sends = sim.sends()
            record = next((r for r in sends[seen:] if r.state == "dropped"), None)
            seen = len(sends)
        if record is not None:
            yield sim, record
            found += 1
            if found == count:
                return
    pytest.fail(f"only {found} of {count} seeds produced a send that was never acknowledged")


def test_send_stays_outstanding_and_no_new_send_before_30_seconds():
    for sim, record in _withheld_cases(CASES):
        station = record.station
        start = record.sent_at
        for offset in (10.0, 29.0, 29.999):
            sim.run_until(start + offset)
            assert _outstanding_price(sim.status(station)) == record.price, (
                f"send {record.send_id!r} stopped being outstanding {offset} s after it was made")
        sim.run_until(start + ABANDON_AFTER)
        assert not _sends_started_between(sim, record, start, start + ABANDON_AFTER), (
            "a new send was made to the station while the earlier send was still outstanding")


def test_send_is_abandoned_at_exactly_30_seconds_and_held_price_is_unchanged():
    for sim, record in _withheld_cases(CASES):
        station = record.station
        start = record.sent_at
        sim.run_until(start + ABANDON_AFTER - 0.001)
        held_before = _held(sim.status(station))
        applied_before = sim.applied_price(station)
        sim.run_until(start + ABANDON_AFTER)
        status = sim.status(station)
        assert _held(status) == held_before
        assert sim.applied_price(station) == applied_before
        outstanding = _outstanding_price(status)
        if outstanding is not None:
            # Still outstanding only if a fresh send was made at this very instant.
            assert any(r.station == station and r.index > record.index
                       and r.sent_at == start + ABANDON_AFTER and r.price == outstanding
                       for r in sim.sends()), "send was not abandoned at 30 seconds"


def test_decision_logic_may_send_again_after_abandonment():
    checked = 0
    for sim, record in _withheld_cases(CASES):
        station = record.station
        start = record.sent_at
        sim.run_until(start + ABANDON_AFTER)
        status = sim.status(station)
        desired, held = _desired(status), _held(status)
        sim.run_until(start + 330.0)
        later_changes = [c for c in sim.changes()
                         if c.station == station and c.time > start + ABANDON_AFTER]
        if later_changes or desired == held:
            continue
        resent = [r for r in sim.sends()
                  if r.station == station and r.index > record.index
                  and r.sent_at >= start + ABANDON_AFTER]
        assert resent, "no new send to the station after the send was abandoned"
        assert resent[0].price == desired
        checked += 1
    assert checked, "no case left a price still to send after abandonment"
