"""GASV4ACCJ-4: a changed desired price is sent to a station within 120 seconds.

Driven only through nrvv_env: prices are set by the simulated pricing source, and
sends and acknowledgements come from the simulated transport.
"""

import importlib

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
RUN_UNTIL = 2400.0  # the last change is at most 1860 s; the 120 s window ends before this
SEND_WINDOW = 120.0


def _run(seed, **options):
    # app keeps its state at module level, so reload it to start each run from nothing
    module = importlib.reload(app)
    sim = Simulation(seed, **options)
    sim.connect(module)
    sim.run_until(RUN_UNTIL)
    return sim


def _acknowledged_price(sim, station, at):
    # price of the last acknowledgement for station that arrived before at (acks are in send order)
    price = None
    for ack in sim.acks():
        if ack.station == station and ack.ack_arrived_at < at:
            price = ack.price
    return price


def _next_change_time(changes, index):
    station = changes[index].station
    for later in changes[index + 1:]:
        if later.station == station:
            return later.time
    return float('inf')


def _lost_ack_time(sim, station, price, at):
    # when station stops holding price: its first later acknowledgement of a different price
    times = [ack.ack_arrived_at for ack in sim.acks()
             if ack.station == station and ack.price != price and ack.ack_arrived_at > at]
    return min(times, default=float('inf'))


def _check_sent_within_window(seed, **options):
    # every change to a price the station has not acknowledged must be sent within SEND_WINDOW
    checks = 0
    sim = _run(seed, **options)
    changes = sim.changes()
    sends = sim.sends()
    for index, change in enumerate(changes):
        if _acknowledged_price(sim, change.station, change.time) == change.price:
            continue  # the station already holds this price
        if _next_change_time(changes, index) <= change.time + SEND_WINDOW:
            continue  # a later change inside the window supersedes this price
        checks += 1
        deadline = change.time + SEND_WINDOW
        sent = [s for s in sends
                if s.station == change.station and s.price == change.price
                and change.time <= s.sent_at <= deadline]
        assert sent, ('seed %d: price %d set for %s at %.3f s was not sent within %d s'
                      % (seed, change.price, change.station, change.time, SEND_WINDOW))
    return checks


def test_changed_price_is_sent_to_station_within_120_seconds():
    checks = sum(_check_sent_within_window(seed) for seed in SEEDS)
    assert checks > 0


def test_changed_price_is_sent_within_120_seconds_under_heavy_loss():
    checks = sum(_check_sent_within_window(seed, drop_probability=0.5) for seed in SEEDS)
    assert checks > 0


def test_acknowledged_price_is_not_sent_again():
    checks = 0
    for seed in SEEDS:
        sim = _run(seed)
        changes = sim.changes()
        sends = sim.sends()
        for index, change in enumerate(changes):
            station, price, at = change.station, change.price, change.time
            if _acknowledged_price(sim, station, at) != price:
                continue  # the station has not acknowledged this price
            checks += 1
            # the station holds price until a different price is acknowledged or the next change
            stop = min(_next_change_time(changes, index), _lost_ack_time(sim, station, price, at))
            resent = [s for s in sends
                      if s.station == station and s.price == price and at <= s.sent_at < stop]
            assert not resent, ('seed %d: acknowledged price %d for %s was sent again at %.3f s'
                                % (seed, price, station, resent[0].sent_at))
    assert checks > 0
