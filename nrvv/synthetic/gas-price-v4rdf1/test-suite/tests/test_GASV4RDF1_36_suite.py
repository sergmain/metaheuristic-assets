import app
from nrvv_env import Simulation

STATIONS = ('alpha', 'beta')


def _make_server(send_update, send_pricing_notice):
    factory = getattr(app, 'make_server', None)
    if callable(factory):
        return factory(send_update, send_pricing_notice)
    for name in sorted(dir(app)):
        candidate = getattr(app, name)
        if not (isinstance(candidate, type) and candidate.__module__ == app.__name__):
            continue
        try:
            server = candidate(send_update, send_pricing_notice)
        except TypeError:
            continue
        if all(callable(getattr(server, m, None))
               for m in ('set_desired_price', 'receive_acknowledgement', 'query_station_state')):
            return server
    raise AssertionError('app provides no server taking the send_update and send_pricing_notice ports')


def _state(sim, station):
    confirmed, desired, outstanding = sim.query(station)
    return confirmed, desired, outstanding


def _sent_to(sim, station, start=0):
    return [u for u in sim.sent[start:] if u.station == station]


def test_no_update_sent_when_confirmed_equals_desired_at_setup():
    for seed in range(5):
        price = 10 + seed
        sim = Simulation(seed, _make_server, STATIONS, script=[[]])
        sim.server.receive_acknowledgement('alpha', price)
        sim.server.set_desired_price('alpha', price)
        sim.run(max_steps=100)
        assert _sent_to(sim, 'alpha') == []
        assert _state(sim, 'alpha') == (price, price, 0)


def test_no_update_sent_when_desired_changed_and_restored_to_confirmed():
    for seed in range(5):
        price = 20 + seed
        sim = Simulation(seed, _make_server, STATIONS, script=[[]])
        sim.server.receive_acknowledgement('alpha', price)
        sim.server.set_desired_price('alpha', price + 1)
        sent_before_restore = len(sim.sent)
        sim.server.set_desired_price('alpha', price)
        assert _sent_to(sim, 'alpha', sent_before_restore) == []
        confirmed, desired, _ = _state(sim, 'alpha')
        assert (confirmed, desired) == (price, price)


def test_confirmed_station_gets_no_update_while_other_station_is_updated():
    for seed in range(5):
        price = 40 + seed
        sim = Simulation(seed, _make_server, STATIONS, script=[[('beta', 77)]])
        sim.server.receive_acknowledgement('alpha', price)
        sim.server.set_desired_price('alpha', price)
        sim.run(max_steps=1000)
        assert _sent_to(sim, 'alpha') == []
        assert any(u.price == 77 for u in _sent_to(sim, 'beta'))
        assert _state(sim, 'alpha') == (price, price, 0)
