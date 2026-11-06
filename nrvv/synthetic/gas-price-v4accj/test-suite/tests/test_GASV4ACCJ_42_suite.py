'''GASV4ACCJ-42: an outstanding send is abandoned after 30 s without acknowledgement (GASV4ACCJ-15).

The send is withheld from acknowledgement by making the station unreachable at the
moment of the send, so the environment never delivers it and never acknowledges it.
'''
import app
from nrvv_env import Simulation

STATION = 'S1'
FIRST_PRICE = 100
WITHHELD_PRICE = 200
ABANDON_AFTER = 30
SEEDS = range(1, 40)


def _make_server(ports):
    if hasattr(app, 'set_desired_price'):
        if hasattr(app, 'connect'):
            app.connect(ports)
        return app
    cls = next(v for v in vars(app).values() if isinstance(v, type) and hasattr(v, 'set_desired_price'))
    try:
        server = cls(ports)
    except TypeError:
        server = cls()
        if hasattr(server, 'connect'):
            server.connect(ports)
    return server


def _new_sim(seed):
    return Simulation(seed, _make_server, horizon=0, loss_rate=0.0)


def _windows(count):
    # (seed, start) pairs where S1 is unreachable for at least 100 s starting at or after 100 s.
    found = []
    for seed in SEEDS:
        sim = _new_sim(seed)
        for start, end in sim.unreachable_intervals(STATION):
            if start >= 100 and end - start >= 100:
                found.append((seed, start))
                break
        if len(found) == count:
            break
    assert found, 'no seed gives a suitable unreachable window'
    return found


def _field(status, *names):
    for name in names:
        if isinstance(status, dict):
            if name in status:
                return status[name]
        elif hasattr(status, name):
            return getattr(status, name)
    raise AssertionError('station status has none of %s: %r' % (names, status))


def _status(sim):
    query = getattr(sim.server, 'query_station_status', None)
    if query is None:
        query = app.query_station_status
    return query(STATION)


def _held(status):
    return _field(status, 'held_price', 'held')


def _outstanding(status):
    return _field(status, 'outstanding_send', 'outstanding')


def _advance_until_sent(sim, price, limit):
    while True:
        found = [r for r in sim.sends if r.station_id == STATION and r.price == price]
        if found:
            return found[0]
        assert sim.now < limit, 'no send of price %d by second %d' % (price, limit)
        sim.step()


def _withheld_send(seed, start):
    sim = _new_sim(seed)
    sim.server.set_desired_price(STATION, FIRST_PRICE)
    sim.advance_to(start - 1)
    assert _held(_status(sim)) == FIRST_PRICE, 'first price not acknowledged before the unreachable window'
    sim.advance_to(start + 1)
    sim.server.set_desired_price(STATION, WITHHELD_PRICE)
    sent = _advance_until_sent(sim, WITHHELD_PRICE, start + 60)
    t0 = sent.sent_at
    assert _outstanding(_status(sim)), 'send is not outstanding right after it was made'
    return sim, t0


def test_outstanding_send_stays_outstanding_before_30_seconds():
    for seed, start in _windows(3):
        sim, t0 = _withheld_send(seed, start)
        for t in range(t0 + 1, t0 + ABANDON_AFTER):
            sim.advance_to(t)
            assert _outstanding(_status(sim)), 'send no longer outstanding at +%d s' % (t - t0)


def test_no_new_send_while_send_is_outstanding_under_30_seconds():
    for seed, start in _windows(3):
        sim, t0 = _withheld_send(seed, start)
        sim.advance_to(t0 + ABANDON_AFTER - 1)
        later = [r for r in sim.sends
                 if r.station_id == STATION and t0 < r.sent_at <= t0 + ABANDON_AFTER - 1]
        assert not later, 'new send made while the earlier send was outstanding'


def test_send_abandoned_exactly_at_30_seconds():
    for seed, start in _windows(3):
        sim, t0 = _withheld_send(seed, start)
        sim.advance_to(t0 + ABANDON_AFTER - 1)
        assert _outstanding(_status(sim)), 'send already abandoned before 30 s'
        sim.advance_to(t0 + ABANDON_AFTER)
        new_sends = [r for r in sim.sends if r.station_id == STATION and r.sent_at == t0 + ABANDON_AFTER]
        # A new send at exactly +30 s is only possible if the old send was already abandoned.
        assert new_sends or not _outstanding(_status(sim)), 'send still outstanding at 30 s'


def test_held_price_unchanged_by_abandonment():
    for seed, start in _windows(3):
        sim, t0 = _withheld_send(seed, start)
        sim.advance_to(t0 + ABANDON_AFTER - 1)
        before = _held(_status(sim))
        sim.advance_to(t0 + ABANDON_AFTER)
        after = _held(_status(sim))
        assert before == after == FIRST_PRICE, 'held price changed by abandonment: %r -> %r' % (before, after)


def test_decision_may_send_again_after_abandonment():
    for seed, start in _windows(3):
        sim, t0 = _withheld_send(seed, start)
        sim.advance_to(t0 + 90)
        again = [r for r in sim.sends
                 if r.station_id == STATION and t0 + ABANDON_AFTER <= r.sent_at <= t0 + 90]
        assert again, 'decision logic did not send again after the send was abandoned'
        assert again[0].price == WITHHELD_PRICE
