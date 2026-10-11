"""Acceptance checks for GASV4ACCJ-47 (requirement GASV4ACCJ-11).

Desired price is a per-station overwrite register: a new price is accepted at
once and overwrites the register, even while an earlier update is unacknowledged.
"""

import app
from nrvv_env import Simulation

SEEDS = range(12)
OUTSTANDING = ("in_transit", "delivered")
STEP_LIMIT = 100000


def _accepted(result):
    if result is True:
        return True
    text = str(getattr(result, "name", result)).lower()
    return "accept" in text and "reject" not in text


def _desired_price(status):
    if isinstance(status, dict):
        return status["desired_price"]
    return status.desired_price


def _replay(tag, seed):
    """Run one seeded simulation against app, reading the station right after each price change.

    An observation records whether the station had an unacknowledged send just before
    the change (busy), the earlier changes to that station (prior), the server's result,
    and the desired price read straight after the change.
    """
    sim = Simulation(seed, stations=(f"{tag}-a", f"{tag}-b", f"{tag}-c"), changes=40)
    sim.connect(app)
    observations = []
    for _ in range(STEP_LIMIT):
        busy = {r.station for r in sim.sends() if r.state in OUTSTANDING}
        count = len(sim.changes())
        if not sim.step():
            break
        if len(sim.changes()) == count:
            continue
        change = sim.changes()[-1]
        observations.append({
            "change": change,
            "result": change.result,
            "busy": change.station in busy,
            "prior": [c for c in sim.changes()[:-1] if c.station == change.station],
            "desired_after": _desired_price(sim.status(change.station)),
        })
    else:
        raise RuntimeError("simulation did not finish")
    return sim, observations


def _busy_observations(name):
    found = []
    for seed in SEEDS:
        _, observations = _replay(f"{name}{seed}", seed)
        found.extend(o for o in observations if o["busy"] and o["prior"])
    return found


def test_price_accepted_at_once_while_earlier_update_unacknowledged():
    observed = _busy_observations("accept")
    assert observed, "no seed produced a price change while an earlier update was unacknowledged"
    for o in observed:
        assert _accepted(o["result"]), f"change was not accepted: {o['change']}"


def test_desired_price_reads_new_value_right_after_each_change():
    total = 0
    for seed in SEEDS:
        _, observations = _replay(f"read{seed}", seed)
        for o in observations:
            total += 1
            assert o["desired_after"] == o["change"].price, f"stale register: {o['change']}"
    assert total > 0


def test_second_price_while_first_unacknowledged_is_accepted_and_read_back():
    observed = _busy_observations("second")
    assert observed, "no seed produced a second price while the first was unacknowledged"
    for o in observed:
        assert _accepted(o["prior"][-1].result), f"first price was not accepted: {o['prior'][-1]}"
        assert _accepted(o["result"]), f"second price was not accepted: {o['change']}"
        assert o["desired_after"] == o["change"].price
        assert o["change"].price != o["prior"][-1].price


def test_register_keeps_only_most_recent_price_per_station():
    for seed in SEEDS:
        sim, _ = _replay(f"latest{seed}", seed)
        last = {}
        for change in sim.changes():
            last[change.station] = change.price
        assert last, "no price changes were made"
        for station, price in last.items():
            assert _desired_price(sim.status(station)) == price, f"register holds an old price for {station}"


def test_no_price_change_is_rejected_because_of_outstanding_sends():
    total = 0
    for seed in SEEDS:
        _, observations = _replay(f"intake{seed}", seed)
        for o in observations:
            total += 1
            assert _accepted(o["result"]), f"change was rejected: {o['change']}"
    assert total > 0
