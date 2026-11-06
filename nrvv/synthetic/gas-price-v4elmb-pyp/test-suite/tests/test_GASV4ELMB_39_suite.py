"""GASV4ELMB-39: a price update superseded before it is sent is never sent."""
import app
from nrvv_env import Simulation

EARLIER, OLD, NEW = 5, 7, 9
SEEDS = range(8)
OUTAGE = (1, 30)


def _scenario(seed, script):
    station = 'S%d' % seed
    sim = Simulation(app, seed, stations=[station])
    sim.script = [(tick, station, price) for tick, price in script]
    sim._script_by_tick = {}
    for tick, s, price in sim.script:
        sim._script_by_tick.setdefault(tick, []).append((s, price))
    sim.last_change_tick = max(tick for tick, _, _ in sim.script)
    sim.outages = {station: [OUTAGE]}
    sim.run()
    return station, sim


def test_superseded_unsent_price_is_never_sent():
    for seed in SEEDS:
        station, sim = _scenario(seed, [(1, EARLIER), (2, OLD), (3, NEW)])
        sent = [s for s in sim.sends if s.station == station]
        assert all(s.price != OLD for s in sent), (
            'seed %d: superseded price sent: %r' % (seed, [(s.tick, s.seq, s.price) for s in sent]))
        assert all(s.price == NEW for s in sent if s.seq > 1), (
            'seed %d: only the newer price may follow the earlier one: %r'
            % (seed, [(s.tick, s.seq, s.price) for s in sent]))
        assert any(s.price == NEW for s in sent), 'seed %d: newer price never sent' % seed


def test_superseded_price_submitted_in_same_tick_is_never_delivered():
    for seed in SEEDS:
        station, sim = _scenario(seed, [(1, EARLIER), (2, OLD), (2, NEW)])
        sent = [s for s in sim.sends if s.station == station]
        delivered = [d.price for d in sim.deliveries[station]]
        assert all(s.price != OLD for s in sent), (
            'seed %d: superseded price sent: %r' % (seed, [(s.tick, s.seq, s.price) for s in sent]))
        assert OLD not in delivered, 'seed %d: superseded price delivered: %r' % (seed, delivered)


def test_newer_price_converges_after_superseded_update_dropped():
    for seed in SEEDS:
        station, sim = _scenario(seed, [(1, EARLIER), (2, OLD), (3, NEW)])
        assert sim.final_display_mismatches() == [], (
            'seed %d: shown price differs from newer desired price: %r'
            % (seed, sim.final_display_mismatches()))
        assert all(s.price != OLD for s in sim.sends if s.station == station), (
            'seed %d: superseded price sent' % seed)
