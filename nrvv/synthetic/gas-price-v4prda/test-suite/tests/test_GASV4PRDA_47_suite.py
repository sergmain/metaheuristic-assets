"""GASV4PRDA-47: at most one unacknowledged price update per station (GASV4PRDA-3).

The outstanding updates of a station are read from the environment's logs:
sent sequence numbers (send port) minus acknowledged ones (acknowledgement calls).
"""

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4)

CONFIGS = (
    {},  # defaults: loss, duplicates, station outages
    {"loss_rate": 0.3, "duplicate_rate": 0.4, "outages": False},
    {"loss_rate": 0.2, "outages": True, "change_rate": 0.4},
)


def _outstanding(sim, station_id, t):
    """Sequence numbers sent to the station up to time t and not acknowledged by time t."""
    sent = {c.sequence_number for c in sim.send_calls if c.station_id == station_id and c.time <= t}
    acked = {a.sequence_number for a in sim.ack_calls if a.station_id == station_id and a.time <= t}
    return sent - acked


def _run_checking_outstanding(sim, seconds):
    """Run second by second; after each second no station has more than one outstanding update."""
    peak = {sid: 0 for sid in sim.stations}
    for _ in range(seconds):
        t = sim.step()
        for sid in sim.stations:
            count = len(_outstanding(sim, sid, t))
            assert count <= 1, f"station {sid} has {count} unacknowledged updates at t={t}"
            peak[sid] = max(peak[sid], count)
    return peak


def test_second_price_waits_while_first_update_unacknowledged():
    # Every transmission is lost, so A is never acknowledged. B and C are issued meanwhile.
    for seed in SEEDS:
        sim = Simulation(
            seed,
            app,
            stations=1,
            change_rate=0.5,
            horizon=200,
            loss_rate=1.0,
            duplicate_rate=0.0,
            outages=False,
        )
        sim.run(200)
        changes = [c for c in sim.central.changes if c.station_id == "S1"]
        assert len(changes) >= 3, "scenario needs A, B and C"

        sent = [c for c in sim.send_calls if c.station_id == "S1"]
        assert sent, "update A was never sent"
        # Only A (one sequence number, A's price) is ever sent; B and C are held back.
        assert {c.sequence_number for c in sent} == {sent[0].sequence_number}
        assert {c.price for c in sent} == {changes[0].price}
        assert sent[0].time == changes[0].time
        # Nothing was acknowledged, nothing reached the station.
        assert sim.ack_calls == []
        assert sim.stations["S1"].received == []
        # The service reports exactly one unacknowledged update for S1 throughout.
        for t in range(changes[0].time, sim.now + 1):
            assert len(_outstanding(sim, "S1", t)) == 1


def test_at_most_one_unacknowledged_update_per_station():
    for config in CONFIGS:
        for seed in SEEDS:
            sim = Simulation(seed, app, stations=2, horizon=300, **config)
            peak = _run_checking_outstanding(sim, 300)
            # The property is exercised: some update was really outstanding.
            assert max(peak.values()) == 1, f"no outstanding update seen: {config} seed={seed}"


def test_next_price_is_sent_only_after_previous_is_acknowledged():
    # Reliable transport: every update is delivered and acknowledged.
    for seed in SEEDS:
        sim = Simulation(
            seed,
            app,
            stations=2,
            horizon=200,
            change_rate=0.2,
            loss_rate=0.0,
            duplicate_rate=0.0,
            outages=False,
        )
        sim.run(260)
        for sid in sim.stations:
            sent = [c for c in sim.send_calls if c.station_id == sid]
            for prev, nxt in zip(sent, sent[1:]):
                if nxt.sequence_number != prev.sequence_number:
                    acked_at = [
                        a.time
                        for a in sim.ack_calls
                        if a.station_id == sid and a.sequence_number == prev.sequence_number
                    ]
                    assert acked_at, f"update {prev.sequence_number} never acknowledged"
                    assert min(acked_at) <= nxt.time, (
                        f"update {nxt.sequence_number} sent at {nxt.time} before "
                        f"update {prev.sequence_number} was acknowledged"
                    )
            # The latest desired price is eventually shown by the station.
            assert sim.stations[sid].display == sim.central.desired[sid]
