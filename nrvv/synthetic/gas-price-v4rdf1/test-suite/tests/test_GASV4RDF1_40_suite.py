'''Tests for GASV4RDF1-11: a new desired price is accepted at any time, without waiting.'''

import inspect
from collections.abc import Mapping

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)
STATION = 'station-1'


def _make_server_factory():
    server_classes = [value for value in vars(app).values()
                      if inspect.isclass(value) and callable(getattr(value, 'set_desired_price', None))]
    assert server_classes, 'app defines no class with a set_desired_price method'
    server_class = server_classes[0]
    return lambda send_update, send_pricing_notice: server_class(send_update, send_pricing_notice)


def _new_simulation(seed):
    return Simulation(seed, _make_server_factory(), [STATION], script=[[]])


def _desired(sim, station):
    state = sim.query(station)
    if isinstance(state, Mapping):
        return [value for key, value in state.items() if 'desired' in str(key).lower()][0]
    if hasattr(state, '_fields'):
        return [getattr(state, name) for name in state._fields if 'desired' in name][0]
    return tuple(state)[1]  # confirmed, desired, outstanding


def test_second_price_replaces_first_while_update_unacknowledged():
    for seed in SEEDS:
        sim = _new_simulation(seed)
        sim.server.set_desired_price(STATION, 100)
        assert len(sim.sent) == 1, 'the first price should be sent while nothing is outstanding'
        sim.server.set_desired_price(STATION, 200)
        assert _desired(sim, STATION) == 200
        sim.run(max_steps=1000)
        assert _desired(sim, STATION) == 200
        assert [update.price for update in sim.sent] == [100, 200]
        assert sim.last_ack(STATION).price == 200


def test_set_calls_return_without_waiting_for_acknowledgements():
    for seed in SEEDS:
        sim = _new_simulation(seed)
        # No simulation step runs between the calls, so a call that waited for an
        # acknowledgement could never return; reaching the asserts shows it did not wait.
        sim.server.set_desired_price(STATION, 100)
        sim.server.set_desired_price(STATION, 200)
        assert sim.clock.now == 0
        assert sim.delivered_updates == []
        assert sim.delivered_acks == []
        assert _desired(sim, STATION) == 200


def test_intermediate_unsent_price_is_dropped():
    for seed in SEEDS:
        sim = _new_simulation(seed)
        sim.server.set_desired_price(STATION, 100)
        sim.server.set_desired_price(STATION, 150)
        sim.server.set_desired_price(STATION, 200)
        assert _desired(sim, STATION) == 200
        sim.run(max_steps=1000)
        assert [update.price for update in sim.sent] == [100, 200]
        assert _desired(sim, STATION) == 200


def test_scheduled_client_calls_end_with_newest_price():
    for seed in SEEDS:
        sim = Simulation(seed, _make_server_factory(), [STATION],
                         script=[[(STATION, 100), (STATION, 200)]])
        sim.run(max_steps=1000)
        assert [call.price for call in sim.client_calls] == [100, 200]
        assert _desired(sim, STATION) == 200
        assert sim.sent[-1].price == 200
        assert sim.last_ack(STATION).price == 200
