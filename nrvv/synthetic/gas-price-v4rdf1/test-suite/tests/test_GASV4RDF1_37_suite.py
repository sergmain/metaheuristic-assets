import app
from nrvv_env import Simulation

OLD_PRICE = 100
NEW_PRICE = 500
SEEDS = range(10)
MAX_STEPS = 20000


def _drive_to_quiet(sim):
    sim.run(max_steps=MAX_STEPS)
    assert sim.is_quiet(), 'service and station did not finish their exchanges within %d steps' % MAX_STEPS


def test_station_holding_older_price_displays_new_price():
    for seed in SEEDS:
        sim = Simulation(app, seed, stations=('S1',), script=[('S1', OLD_PRICE), ('S1', NEW_PRICE)])
        # advance until the station shows the older price, then let the new price be set
        while sim.displayed('S1') != OLD_PRICE and len(sim.call_log) < 2 and sim.step():
            pass
        _drive_to_quiet(sim)
        assert sim.displayed('S1') == NEW_PRICE, 'seed %d: station shows %r' % (seed, sim.displayed('S1'))


def test_last_acknowledgement_carries_new_price():
    for seed in SEEDS:
        sim = Simulation(app, seed, stations=('S1',), script=[('S1', OLD_PRICE), ('S1', NEW_PRICE)])
        _drive_to_quiet(sim)
        assert sim.last_ack_price('S1') == NEW_PRICE, 'seed %d: last ack %r' % (seed, sim.last_ack_price('S1'))
        assert sim.displayed('S1') == NEW_PRICE, 'seed %d: station shows %r' % (seed, sim.displayed('S1'))


def test_sent_updates_are_price_only_updates_to_the_station():
    for seed in SEEDS:
        sim = Simulation(app, seed, stations=('S1',), script=[('S1', OLD_PRICE), ('S1', NEW_PRICE)])
        _drive_to_quiet(sim)
        assert sim.sent_log, 'seed %d: no update was sent to the station' % seed
        assert not sim.in_flight(), 'seed %d: sent updates were not all delivered' % seed
        for sent in sim.sent_log:
            assert sent.station == 'S1', 'seed %d: update sent to %r' % (seed, sent.station)
            assert sent.price in (OLD_PRICE, NEW_PRICE), 'seed %d: update carries price %r' % (seed, sent.price)
        assert any(sent.price == NEW_PRICE for sent in sim.sent_log), 'seed %d: new price never sent' % seed


def test_newest_price_wins_after_several_changes():
    prices = (100, 300, 700, 900)
    for seed in SEEDS:
        sim = Simulation(app, seed, stations=('S1',), script=[('S1', p) for p in prices])
        _drive_to_quiet(sim)
        assert sim.displayed('S1') == prices[-1], 'seed %d: station shows %r' % (seed, sim.displayed('S1'))
        assert sim.last_ack_price('S1') == prices[-1], 'seed %d: last ack %r' % (seed, sim.last_ack_price('S1'))


def test_convergence_holds_with_traffic_to_another_station():
    for seed in SEEDS:
        script = [('S1', OLD_PRICE), ('S2', OLD_PRICE), ('S1', NEW_PRICE), ('S2', NEW_PRICE)]
        sim = Simulation(app, seed, stations=('S1', 'S2'), script=script)
        _drive_to_quiet(sim)
        assert sim.displayed('S1') == NEW_PRICE, 'seed %d: S1 shows %r' % (seed, sim.displayed('S1'))
        assert sim.displayed('S2') == NEW_PRICE, 'seed %d: S2 shows %r' % (seed, sim.displayed('S2'))
        for sent in sim.sent_log:
            assert sent.station in ('S1', 'S2'), 'seed %d: update sent to %r' % (seed, sent.station)
            assert sent.price in (OLD_PRICE, NEW_PRICE), 'seed %d: update carries price %r' % (seed, sent.price)
