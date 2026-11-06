'''Suite for GASV4E2CM-9: no price update for a desired price the station already confirmed.'''
import app
from nrvv_env import DMAX, Simulation

PRICE = 42
SEEDS = (1, 2, 3, 4, 5)
TICKS_AFTER_RESEND = 60  # long enough to observe any timeout expiry


def _confirmed_price(status):
    if isinstance(status, dict):
        fields = list(status.items())
    else:
        fields = [(name, getattr(status, name)) for name in dir(status) if not name.startswith('_')]
    for name, value in fields:
        if 'confirm' in name.lower() and not callable(value):
            return value
    raise AssertionError('status exposes no confirmed price: %r' % (status,))


def test_resend_of_confirmed_price_sends_no_update():
    for seed in SEEDS:
        sim = Simulation(app, seed, stations=('S1',), loss=0.0, outage=0.0)
        sim.set_desired_price('S1', PRICE)
        assert sim.quiesce(), 'first update never settled (seed %d)' % seed
        assert sim.acks_per_station()['S1'] >= 1, 'no acknowledgement (seed %d)' % seed
        assert _confirmed_price(sim.status('S1')) == PRICE
        sends_before = len(sim.sent_to('S1'))
        sim.set_desired_price('S1', PRICE)
        for _ in range(TICKS_AFTER_RESEND):
            sim.tick()
        assert len(sim.sent_to('S1')) == sends_before, 'update sent again (seed %d)' % seed
        assert _confirmed_price(sim.status('S1')) == PRICE


def test_resend_of_confirmed_price_sends_no_update_on_lossy_transport():
    for seed in SEEDS:
        sim = Simulation(app, seed)
        sim.set_desired_price('S2', PRICE)
        assert sim.quiesce(bound=1000), 'first update never settled (seed %d)' % seed
        assert sim.acks_per_station()['S2'] >= 1, 'no acknowledgement (seed %d)' % seed
        assert _confirmed_price(sim.status('S2')) == PRICE
        sends_before = len(sim.sent_to('S2'))
        sim.set_desired_price('S2', PRICE)
        for _ in range(TICKS_AFTER_RESEND):
            sim.tick()
        assert len(sim.sent_to('S2')) == sends_before, 'update sent again (seed %d)' % seed
        assert _confirmed_price(sim.status('S2')) == PRICE
