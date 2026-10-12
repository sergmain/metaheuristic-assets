import re
from collections.abc import Mapping

import app
from nrvv_env import SERVER_METHODS, Simulation


def _norm(name):
    return re.sub(r'[^a-z]', '', name.lower())


def _value(v):
    return v() if callable(v) else v


def _as_field(token, v):
    if token == 'outstanding' and isinstance(v, (list, tuple, set, dict)):
        return len(v)
    return v


def _find(result, token, index):
    if isinstance(result, Mapping):
        for key, value in result.items():
            if token in _norm(str(key)):
                return _as_field(token, _value(value))
        raise AssertionError(f'no {token} field in {result!r}')
    names = [n for n in dir(result) if not n.startswith('_') and token in _norm(n)]
    if names:
        return _as_field(token, _value(getattr(result, names[0])))
    if isinstance(result, (tuple, list)) and len(result) > index:
        return _as_field(token, _value(result[index]))
    raise AssertionError(f'no {token} field in {result!r}')


def _read(sim, station):
    result = sim.query(station)
    return {'outstanding': _find(result, 'outstanding', 2), 'up_to_date': _find(result, 'uptodate', 4)}


def _server_target():
    for obj in vars(app).values():
        if isinstance(obj, type) and obj.__module__ == app.__name__ and all(
                callable(getattr(obj, m, None)) for m in SERVER_METHODS):
            return obj
    return app


def _server_factory(send_update):
    target = _server_target()
    if isinstance(target, type):
        try:
            return target(send_update)
        except TypeError:
            return target()
    return target


def test_up_to_date_true_after_single_update_acknowledged():
    for seed in (1, 2, 3):
        sim = Simulation(seed, _server_factory, stations=['S1'], changes=[(1, 'S1', 4)],
                         loss_downlink=0.0, loss_uplink=0.0)
        assert sim.run_until_quiet()
        assert any(tx.station == 'S1' for tx in sim.transmissions)
        state = _read(sim, 'S1')
        assert state['outstanding'] == 0
        assert state['up_to_date'] is True


def test_up_to_date_false_while_outstanding_entry_remains():
    cases = [dict(loss_downlink=1.0, loss_uplink=0.0), dict(loss_downlink=0.0, loss_uplink=1.0)]
    for seed, loss in enumerate(cases, start=21):
        sim = Simulation(seed, _server_factory, stations=['S1'], changes=[(1, 'S1', 4)], **loss)
        sim.run(20)
        assert sim.transmissions
        state = _read(sim, 'S1')
        assert state['outstanding'] >= 1
        assert state['up_to_date'] is False


def test_up_to_date_flag_tracks_outstanding_list_under_loss():
    for seed in range(1, 6):
        sim = Simulation(seed, _server_factory, stations=3, duration=40, loss_downlink=0.3, loss_uplink=0.3)
        for _ in range(60):
            sim.step()
            for name in sim.stations:
                state = _read(sim, name)
                if state['outstanding'] > 0:
                    assert state['up_to_date'] is False
                if state['up_to_date'] is True:
                    assert state['outstanding'] == 0
        assert sim.run_until_quiet()
        for name in sim.stations:
            if any(tx.station == name for tx in sim.transmissions):
                assert _read(sim, name)['up_to_date'] is True


def test_up_to_date_true_only_after_last_of_several_acks():
    for seed in (31, 32, 33):
        sim = Simulation(seed, _server_factory, stations=['S1'],
                         changes=[(1, 'S1', 3), (2, 'S1', 6), (3, 'S1', 8)],
                         loss_downlink=0.0, loss_uplink=0.0)
        history = {}
        for _ in range(60):
            now = sim.step()
            history[now] = _read(sim, 'S1')
        sent = [tx for tx in sim.transmissions if tx.station == 'S1']
        assert len(sent) >= 2
        assert any(tx.price == 8 for tx in sent)
        assert all(tx.delivered_at is not None for tx in sent)
        acks = [a for a in sim.acks if a.station == 'S1']
        assert acks and all(a.delivered_at is not None for a in acks)
        last = max(a.delivered_at for a in acks)
        for now in range(1, last):
            assert history[now]['outstanding'] >= 1
            assert history[now]['up_to_date'] is False
        assert history[last]['outstanding'] == 0
        assert history[last]['up_to_date'] is True
