import re
from collections.abc import Mapping

import app
from nrvv_env import ClientChange, SERVER_METHODS, Simulation

SEEDS = (1, 2, 3, 4, 5)


def _norm(name):
    return re.sub(r'[^a-z]', '', str(name).lower())


def _value(v):
    return v() if callable(v) else v


def _up_to_date(result):
    if isinstance(result, Mapping):
        for key, value in result.items():
            if _norm(key) in ('uptodate', 'isuptodate'):
                return _value(value)
    elif not isinstance(result, (tuple, list)):
        for name in dir(result):
            if _norm(name) in ('uptodate', 'isuptodate'):
                return _value(getattr(result, name))
    if isinstance(result, (tuple, list)) and len(result) >= 5:
        return _value(result[4])
    raise AssertionError(f'QueryStation result has no up-to-date flag: {result!r}')


def _attach_server(sim):
    for name in sorted(dir(app)):
        cls = getattr(app, name)
        if (isinstance(cls, type) and cls.__module__ == app.__name__
                and all(callable(getattr(cls, m, None)) for m in SERVER_METHODS)):
            try:
                server = cls(sim.send_update)
            except TypeError:
                server = cls()
            return sim.attach(server)
    return sim.attach(app)


def _scenario(seed):
    station = f'K{seed}'
    sim = Simulation(seed, stations=[station],
                     changes=[ClientChange(1, station, 3), ClientChange(2, station, 7)],
                     loss_downlink=0.0, loss_uplink=0.0)
    _attach_server(sim)
    sim.loss_downlink = 1.0  # update 1 (price 3) is lost on the way to the station
    sim.run(1)
    sim.loss_downlink = 0.0  # update 2 (latest price 7) is delivered
    sim.run(1)
    while sim.in_flight_count():
        sim.step()
    return sim, station


def test_station_not_up_to_date_while_an_earlier_update_is_unacked():
    for seed in SEEDS:
        sim, station = _scenario(seed)
        assert [tx.price for tx in sim.transmissions[:2]] == [3, 7]
        assert sim.outstanding(station) == 1
        assert not _up_to_date(sim.query(station))
        assert sim.run_until_quiet(horizon=200)
        assert sim.outstanding(station) == 0
        assert _up_to_date(sim.query(station))
