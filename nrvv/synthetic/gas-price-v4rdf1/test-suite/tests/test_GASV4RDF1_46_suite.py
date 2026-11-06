import importlib

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)
OVERLAP_SCRIPT = [('S1', 5), ('S1', 7), ('S2', 3), ('S1', 9), ('S2', 3), ('S2', 12), ('S1', 1)]


def _session(seed, script=None, calls=12):
    module = importlib.reload(app)
    sim = Simulation(module, seed, calls=calls, script=script)
    sim.run()
    assert sim.is_quiet(), 'session did not drain'
    return sim


def _is_price(value):
    return type(value) is int


def test_every_update_carries_a_price():
    for seed in SEEDS:
        sim = _session(seed, script=OVERLAP_SCRIPT)
        assert sim.sent_log, 'seed %d: server sent no update' % seed
        for sent in sim.sent_log:
            assert _is_price(sent.price), 'seed %d: update without a plain price: %r' % (seed, sent)


def test_update_carries_the_current_desired_price_only():
    for seed in SEEDS:
        sim = _session(seed, script=OVERLAP_SCRIPT)
        for sent in sim.sent_log:
            assert sent.desired is not None, 'seed %d: update sent before any desired price: %r' % (seed, sent)
            assert sent.price == sent.desired, 'seed %d: update differs from desired price: %r' % (seed, sent)


def test_every_acknowledgement_carries_a_price():
    for seed in SEEDS:
        sim = _session(seed, script=OVERLAP_SCRIPT)
        assert sim.ack_log, 'seed %d: no acknowledgement was read' % seed
        for ack in sim.ack_log:
            assert _is_price(ack.price), 'seed %d: acknowledgement without a plain price: %r' % (seed, ack)
            sent_to_station = {s.price for s in sim.sent_log if s.station == ack.station}
            assert ack.price in sent_to_station, 'seed %d: acknowledgement echoes no sent price: %r' % (seed, ack)


def test_each_update_gets_exactly_one_acknowledgement():
    for seed in SEEDS:
        sim = _session(seed, script=OVERLAP_SCRIPT)
        for name in sim.stations:
            sent = sum(1 for s in sim.sent_log if s.station == name)
            acked = sum(1 for a in sim.ack_log if a.station == name)
            assert acked == sent, 'seed %d: station %s: %d updates, %d acknowledgements' % (seed, name, sent, acked)
            assert sim.pending_acks(name) == 0


def test_station_displays_and_acknowledges_latest_desired_price():
    for seed in SEEDS:
        sim = _session(seed, script=OVERLAP_SCRIPT)
        for name, price in sim.desired.items():
            assert sim.displayed(name) == price, 'seed %d: station %s displays %r, desired %r' % (seed, name, sim.displayed(name), price)
            assert sim.last_ack_price(name) == price, 'seed %d: station %s last ack %r, desired %r' % (seed, name, sim.last_ack_price(name), price)


def test_random_session_keeps_messages_price_only():
    for seed in SEEDS:
        sim = _session(seed, calls=20)
        assert sim.sent_log and sim.ack_log
        for sent in sim.sent_log:
            assert _is_price(sent.price)
            assert sent.price == sent.desired
        for ack in sim.ack_log:
            assert _is_price(ack.price)
