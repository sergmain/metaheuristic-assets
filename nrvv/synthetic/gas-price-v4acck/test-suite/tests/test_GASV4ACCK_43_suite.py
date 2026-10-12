import importlib
import inspect

import app
from nrvv_env import Simulation

SEEDS = range(25)


def _make_server():
    if hasattr(app, 'set_latest_price'):
        return importlib.reload(app)
    for name in dir(app):
        obj = getattr(app, name)
        if inspect.isclass(obj) and name[:1].isupper() and hasattr(obj, 'set_latest_price'):
            return obj()
    raise AssertionError('app provides no server with set_latest_price')


def _view_value(view, word):
    if isinstance(view, dict):
        fields = list(view.items())
    else:
        fields = [(n, getattr(view, n)) for n in dir(view) if not n.startswith('_')]
    for name, value in fields:
        if word in str(name).lower() and not callable(value):
            return value
    raise AssertionError(f'station view has no field containing {word!r}: {view!r}')


def test_single_update_is_sent_once_and_plain_ack_counts_as_delivery():
    for seed in SEEDS:
        sim = Simulation(seed, ['S1'], changes_per_station=(1, 1))
        server = sim.bind(_make_server())
        sim.run_to_end()
        assert len(sim.changes) == 1, f'seed {seed}: expected one change'
        price = sim.changes[0].price
        assert len(sim.sends) == 1, f'seed {seed}: expected one send, got {len(sim.sends)}'
        record = sim.sends[0]
        assert record.station == 'S1' and record.price == price
        assert record.delivered_at is not None, f'seed {seed}: update not delivered'
        assert record.acknowledged_at is not None, f'seed {seed}: plain ack not treated as success'
        assert sim.stations['S1'].held_price == price
        view = server.get_station_view('S1')
        assert _view_value(view, 'acknowledged') == price, f'seed {seed}: ack not recorded'
        assert _view_value(view, 'outstanding') is None, f'seed {seed}: update still outstanding'


def test_each_station_gets_one_update_and_no_resend_after_plain_ack():
    stations = ['A', 'B', 'C']
    for seed in SEEDS:
        sim = Simulation(seed, stations, changes_per_station=(1, 1))
        server = sim.bind(_make_server())
        sim.run_to_end()
        assert sim.send_counts() == {s: 1 for s in stations}, f'seed {seed}: unexpected send counts'
        assert sim.unacknowledged_sends() == [], f'seed {seed}: some update never acknowledged'
        for s in stations:
            price = next(c.price for c in sim.changes if c.station == s)
            assert sim.stations[s].held_price == price
            assert _view_value(server.get_station_view(s), 'acknowledged') == price
