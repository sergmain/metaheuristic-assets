'''Verifies GASV4ACCJ-10: a station holds a price only after its acknowledgement arrives.'''
import importlib

import app
from nrvv_env import Simulation

STATION = 'S1'
SEEDS = range(1, 21)
MIN_CHECKED = 3
WINDOW = 200  # seconds the station is guaranteed reachable in these scenarios


def _field(obj, name):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _held(price):
    status = app.query_station_status(STATION)
    return _field(status, 'held_price') == price


def _outstanding_price():
    status = app.query_station_status(STATION)
    return _field(_field(status, 'outstanding_send'), 'price')


def _new_sim(seed):
    importlib.reload(app)
    return Simulation(seed, app, station_ids=(STATION,), horizon=0, loss_rate=0.0)


def _usable(sim):
    # the station is reachable for the whole scenario window
    return all(start > WINDOW for start, _ in sim.unreachable_intervals(STATION))


def _schedule_change(sim, at, price):
    # desired-price changes come from the environment's change queue; horizon=0 leaves it empty
    sim._push(at, 'change', (STATION, price))


def _sends(sim, price, outcome=None):
    return [s for s in sim.sends if s.price == price and (outcome is None or s.outcome == outcome)]


def _step_until(sim, done):
    while not done():
        if sim.now >= WINDOW:
            raise AssertionError('expected event not reached by second %d' % WINDOW)
        sim.step()


def test_price_is_not_held_until_its_acknowledgement_is_delivered():
    checked = 0
    for seed in SEEDS:
        sim = _new_sim(seed)
        if not _usable(sim):
            continue
        _schedule_change(sim, 10, 100)
        _step_until(sim, lambda: bool(_sends(sim, 100)))
        send = _sends(sim, 100)[0]
        assert send.outcome == 'delivered'
        if send.ack_at <= sim.now:
            continue  # acknowledgement arrives with the send itself: no window to check
        assert not _held(100)
        sim.advance_to(send.ack_at)
        assert _held(100)
        checked += 1
    assert checked >= MIN_CHECKED


def test_later_acknowledgement_resolves_earlier_updates_and_holds_latest_price():
    checked = 0
    for seed in SEEDS:
        sim = _new_sim(seed)
        if not _usable(sim):
            continue
        _schedule_change(sim, 10, 100)
        _step_until(sim, lambda: bool(_sends(sim, 100)))
        first = _sends(sim, 100)[0]
        assert first.outcome == 'delivered'
        sim.advance_to(first.ack_at)
        assert _held(100)

        # the 200 update is lost: it is never acknowledged
        sim.loss_rate = 1.0
        _schedule_change(sim, sim.now + 1, 200)
        _step_until(sim, lambda: bool(_sends(sim, 200)))
        lost = _sends(sim, 200)[0]
        assert lost.outcome == 'lost'

        # the 300 update is delivered; only its acknowledgement is delivered
        sim.loss_rate = 0.0
        _schedule_change(sim, sim.now + 1, 300)
        _step_until(sim, lambda: bool(_sends(sim, 300, 'delivered')))
        latest = _sends(sim, 300, 'delivered')[0]
        if latest.ack_at <= sim.now:
            continue
        assert not _held(300)
        sim.advance_to(latest.ack_at)

        acked = [a.send_id for a in sim.acks]
        assert lost.send_id not in acked
        assert latest.send_id in acked
        assert _held(300)
        assert _outstanding_price() != 200
        checked += 1
    assert checked >= MIN_CHECKED
