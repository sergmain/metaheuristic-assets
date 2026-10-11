'''Tests for GASV4ACCJ-44: the held price changes only on acknowledgement of a send (GASV4ACCJ-12).'''
import pytest

import app
from nrvv_env import Simulation

STATION = 'S1'
WAIT_LIMIT = 300
SEED_COUNT = 3
UNKNOWN_SEND_ID = 'no-such-send-id'


def _server_factory(ports):
    if hasattr(app, 'set_desired_price'):
        connect = getattr(app, 'connect', None)
        if connect is not None:
            connect(ports)
        return app
    classes = [
        value for value in vars(app).values()
        if isinstance(value, type) and value.__module__ == app.__name__
        and hasattr(value, 'set_desired_price')
    ]
    if not classes:
        pytest.fail('app provides no server with set_desired_price')
    try:
        server = classes[0](ports)
    except TypeError:
        server = classes[0]()
    connect = getattr(server, 'connect', None)
    if connect is not None:
        connect(ports)
    return server


def _make_sim(seed):
    # horizon=0 means the environment schedules no desired-price changes of its own.
    return Simulation(seed, _server_factory, horizon=0, loss_rate=0.0)


def _quiet_seeds(count):
    # Seeds where S1 is reachable for the whole wait window, so the send can be acknowledged.
    seeds = []
    seed = 1
    while len(seeds) < count:
        sim = _make_sim(seed)
        if all(sim.is_reachable(STATION, t) for t in range(WAIT_LIMIT)):
            seeds.append(seed)
        seed += 1
    return seeds


def _held_price(sim):
    status = sim.server.query_station_status(STATION)
    for key in ('held_price', 'held'):
        if isinstance(status, dict):
            if key in status:
                return status[key]
        elif hasattr(status, key):
            return getattr(status, key)
    pytest.fail('query_station_status result has no held price: %r' % (status,))


def _send_and_await_ack(sim):
    # Make a price change for S1, then step time until the environment delivers the
    # acknowledgement. Until then the held price must still equal its earlier value.
    before = _held_price(sim)
    price = 137 if before != 137 else 138
    sim.server.set_desired_price(STATION, price)
    while not sim.acks:
        assert sim.now < WAIT_LIMIT, 'no acknowledgement for S1 by second %d' % WAIT_LIMIT
        assert _held_price(sim) == before, 'held price changed before any acknowledgement'
        sim.step()
    return before, price, sim.acks[0]


def test_send_leaves_held_price_unchanged_until_ack():
    for seed in _quiet_seeds(SEED_COUNT):
        sim = _make_sim(seed)
        _, price, _ = _send_and_await_ack(sim)
        assert any(s.station_id == STATION and s.price == price for s in sim.sends)


def test_ack_sets_held_price_to_sent_price():
    for seed in _quiet_seeds(SEED_COUNT):
        sim = _make_sim(seed)
        _, price, ack = _send_and_await_ack(sim)
        sent = [s for s in sim.sends if s.send_id == ack.send_id]
        assert sent and sent[0].station_id == STATION and sent[0].price == price
        assert _held_price(sim) == price


def test_repeat_ack_for_same_send_id_keeps_held_price():
    for seed in _quiet_seeds(SEED_COUNT):
        sim = _make_sim(seed)
        _, price, ack = _send_and_await_ack(sim)
        assert _held_price(sim) == price
        sim.server.acknowledgement_received(STATION, ack.send_id)
        assert _held_price(sim) == price


def test_ack_for_unknown_send_id_keeps_held_price():
    for seed in _quiet_seeds(SEED_COUNT):
        sim = _make_sim(seed)
        _, price, _ = _send_and_await_ack(sim)
        assert _held_price(sim) == price
        assert all(s.send_id != UNKNOWN_SEND_ID for s in sim.sends)
        sim.server.acknowledgement_received(STATION, UNKNOWN_SEND_ID)
        assert _held_price(sim) == price
