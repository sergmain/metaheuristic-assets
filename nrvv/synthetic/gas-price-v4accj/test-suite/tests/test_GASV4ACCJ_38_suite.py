"""Test case GASV4ACCJ-38 for requirement GASV4ACCJ-13: at most one outstanding send per station."""

import app
from nrvv_env import Simulation

TIMEOUT = 30.0  # abandonment timeout of an unacknowledged send
SEEDS = range(1, 31)
MAX_STEPS = 100000


def _sim(tag, seed, drop_probability):
    # The app module keeps its state between simulations, so each run gets a
    # station name that no earlier run used.
    station = f"{tag}-{seed}"
    sim = Simulation(seed, stations=(station,), drop_probability=drop_probability)
    sim.connect(app)
    return sim, station


def _sends(sim, station):
    return [r for r in sim.sends() if r.station == station]


def _unresolved(sim, station):
    """Sends for station that are neither acknowledged nor past their timeout."""
    return [r for r in sim.sends()
            if r.station == station and r.ack_arrived_at is None
            and sim.now < r.sent_at + TIMEOUT]


def _applied(sim, station):
    """Number of planned changes for station that the simulation has applied."""
    return sum(1 for c in sim.changes() if c.station == station)


def _next_change(sim, station):
    """(time, price) of the next planned change for station not yet applied, or None."""
    planned = [(t, p) for t, s, p in sim.schedule() if s == station]
    done = _applied(sim, station)
    return planned[done] if done < len(planned) else None


def _transmitted(sim, station, price, since):
    return any(r.station == station and r.price == price and r.sent_at >= since
               for r in sim.sends())


def _run_until(sim, done):
    for _ in range(MAX_STEPS):
        if done():
            return True
        if not sim.step():
            return done()
    return False


def _scenarios(tag, drop_probability):
    """Per seed, the first moment one station has exactly one unresolved send and its
    next planned change is due before that send times out.

    Yields (sim, station, first_send, (change_time, price)).
    """
    for seed in SEEDS:
        sim, station = _sim(tag, seed, drop_probability)
        for _ in range(MAX_STEPS):
            unresolved = _unresolved(sim, station)
            nxt = _next_change(sim, station)
            if (len(unresolved) == 1 and nxt is not None
                    and sim.now < nxt[0] < unresolved[0].sent_at + TIMEOUT):
                yield sim, station, unresolved[0], nxt
                break
            if not sim.step():
                break


def test_second_update_held_while_first_send_outstanding():
    checked = 0
    for sim, station, first, _ in _scenarios("A38", 0.0):
        applied = _applied(sim, station)
        sends_before = len(_sends(sim, station))
        assert _run_until(sim, lambda: _applied(sim, station) > applied
                          or first.ack_arrived_at is not None)
        if first.ack_arrived_at is not None:
            continue  # acknowledged before the second update arrived
        checked += 1
        assert len(_sends(sim, station)) == sends_before
        assert len(_unresolved(sim, station)) == 1
        # Hold until the first send is acknowledged or times out.
        while first.ack_arrived_at is None and sim.now < first.sent_at + TIMEOUT:
            assert len(_sends(sim, station)) == sends_before
            assert len(_unresolved(sim, station)) == 1
            if not sim.step():
                break
    assert checked > 0


def test_second_update_sent_once_first_send_acknowledged():
    checked = 0
    for sim, station, first, (change_at, price) in _scenarios("B38", 0.0):
        applied = _applied(sim, station)
        assert _run_until(sim, lambda: _applied(sim, station) > applied
                          or first.ack_arrived_at is not None)
        if _applied(sim, station) > applied:
            continue  # the second update arrived first: covered by the hold test
        checked += 1
        assert _run_until(sim, lambda: _applied(sim, station) > applied)
        assert _run_until(sim, lambda: _transmitted(sim, station, price, change_at))
        sent = [r for r in sim.sends()
                if r.station == station and r.price == price and r.sent_at >= change_at]
        assert sent[0].sent_at >= first.ack_arrived_at
    assert checked > 0


def test_second_update_sent_after_timeout_without_acknowledgement():
    checked = 0
    for sim, station, first, (change_at, price) in _scenarios("C38", 1.0):
        applied = _applied(sim, station)
        sends_before = len(_sends(sim, station))
        assert _run_until(sim, lambda: _applied(sim, station) > applied)
        assert len(_sends(sim, station)) == sends_before
        checked += 1
        # Nothing is acknowledged, so the second update waits for the timeout.
        assert _run_until(sim, lambda: len(_sends(sim, station)) > sends_before)
        second = _sends(sim, station)[sends_before]
        assert second.price == price
        assert second.sent_at >= first.sent_at + TIMEOUT
    assert checked > 0
