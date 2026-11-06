"""Tests for GASV4ELMB-17: retransmit an unacknowledged update on timeout with capped backoff."""
from nrvv_env import Simulation

import app

STATION = 'S0'
PRICE = 7
NEVER = float('inf')
SEEDS = (1, 2, 3)


def _start(seed):
    """One station, one scripted change of PRICE at tick 2, transport driven by seed."""
    sim = Simulation(app, seed, stations=[STATION])
    sim._script_by_tick = {2: [(STATION, PRICE)]}
    return sim


def _silent(sim):
    """The station never receives anything, so no acknowledgement can come back."""
    sim.outages = {STATION: [(0, NEVER)]}


def _sends(sim):
    return [s for s in sim.sends if s.station == STATION]


def _gaps(sim):
    ticks = [s.tick for s in _sends(sim)]
    return [b - a for a, b in zip(ticks, ticks[1:])]


def _run(sim, stop, max_ticks=20000):
    """Step until stop(sim) holds; return the reported timeout of the station after each tick."""
    timeouts = {}
    while not stop(sim):
        if sim.tick >= max_ticks:
            raise AssertionError('stop condition not reached by tick %d (seed %r)' % (max_ticks, sim.seed))
        tick = sim.step()
        timeouts[tick] = sim.server_state(STATION)['timeout']
    return timeouts


def test_resends_same_seq_and_price_at_every_expiry():
    for seed in SEEDS:
        sim = _start(seed)
        _silent(sim)
        _run(sim, lambda s: len(_sends(s)) >= 17)
        sends = _sends(sim)
        assert sends[0].seq == 1
        assert [s.retransmission for s in sends] == [False] + [True] * (len(sends) - 1)
        assert all(s.seq == 1 and s.price == PRICE for s in sends), seed


def test_gaps_double_from_base_then_stay_at_cap():
    summary = set()
    for seed in SEEDS:
        sim = _start(seed)
        _silent(sim)
        _run(sim, lambda s: len(_sends(s)) >= 17)
        gaps = _gaps(sim)
        base, cap = gaps[0], gaps[-1]
        assert base >= 1
        assert cap > base, (seed, gaps)
        for k, g in enumerate(gaps):
            assert g == min(base * 2 ** k, cap), (seed, k, gaps)
        assert gaps[-3:] == [cap] * 3, (seed, gaps)
        summary.add((base, cap))
    assert len(summary) == 1


def test_reported_timeout_equals_next_gap():
    for seed in SEEDS:
        sim = _start(seed)
        _silent(sim)
        timeouts = _run(sim, lambda s: len(_sends(s)) >= 13)
        for send, gap in zip(_sends(sim), _gaps(sim)):
            assert timeouts[send.tick] == gap, (seed, send.tick, gap)


def test_acknowledgement_resets_timeout_to_base():
    for seed in SEEDS:
        sim = _start(seed)
        _silent(sim)
        timeouts = _run(sim, lambda s: len(_sends(s)) >= 5)
        first = _sends(sim)[0].tick
        base = timeouts[first]
        sim.outages = {STATION: [(0, sim.tick)]}
        timeouts.update(_run(sim, lambda s: any(a.arrived is not None and a.arrived <= s.tick for a in s.acks)))
        ack = next(a for a in sim.acks if a.arrived is not None)
        assert ack.seq == 1
        grown = [v for t, v in timeouts.items() if first <= t < ack.arrived]
        assert max(grown) > base, (seed, base)
        assert timeouts[ack.arrived] == base, (seed, base)
