'''Suite for GASV4R12A-16: up-to-date status requires an acknowledgement on the desired version.'''
import app
from nrvv_env import Simulation

STATION = 's1'
SEEDS = (1, 7, 42)


def _server(seed):
    sim = Simulation(seed)
    sim.attach(lambda send: app.Server(send_update=send))
    return sim


def _up_to_date(sim):
    status = sim.server.query_station_status(STATION)
    names = ('up_to_date', 'up_to_date_flag', 'is_up_to_date')
    if isinstance(status, dict):
        return bool(next(status[n] for n in names if n in status))
    return bool(next(getattr(status, n) for n in names if hasattr(status, n)))


def test_not_up_to_date_before_any_acknowledgement():
    for seed in SEEDS:
        sim = _server(seed)
        sim.server.accept_desired_price(STATION, sim.rng.randint(1, 1000))
        assert not _up_to_date(sim), 'seed {}'.format(seed)


def test_up_to_date_when_ack_matches_desired_version_and_price():
    for seed in SEEDS:
        sim = _server(seed)
        price = sim.rng.randint(1, 1000)
        version = sim.server.accept_desired_price(STATION, price)
        sim.server.receive_acknowledgement(STATION, version, price)
        assert _up_to_date(sim), 'seed {}'.format(seed)


def test_not_up_to_date_after_desired_version_moves_past_acknowledged_version():
    for seed in SEEDS:
        sim = _server(seed)
        price = sim.rng.randint(1, 1000)
        version = sim.server.accept_desired_price(STATION, price)
        sim.server.receive_acknowledgement(STATION, version, price)
        assert _up_to_date(sim), 'seed {}'.format(seed)
        next_version = sim.server.accept_desired_price(STATION, price)
        assert next_version == version + 1, 'seed {}'.format(seed)
        assert not _up_to_date(sim), 'seed {}'.format(seed)


def test_not_up_to_date_when_ack_names_previous_version_with_same_price():
    for seed in SEEDS:
        sim = _server(seed)
        price = sim.rng.randint(1, 1000)
        old = sim.server.accept_desired_price(STATION, price + 1)
        current = sim.server.accept_desired_price(STATION, price)
        assert current == old + 1, 'seed {}'.format(seed)
        sim.server.receive_acknowledgement(STATION, old, price)
        assert not _up_to_date(sim), 'seed {}'.format(seed)


def test_not_up_to_date_when_ack_displays_other_price():
    for seed in SEEDS:
        sim = _server(seed)
        price = sim.rng.randint(1, 1000)
        version = sim.server.accept_desired_price(STATION, price)
        sim.server.receive_acknowledgement(STATION, version, price + 1)
        assert not _up_to_date(sim), 'seed {}'.format(seed)


def test_up_to_date_recomputed_on_each_acknowledgement():
    for seed in SEEDS:
        sim = _server(seed)
        price = sim.rng.randint(1, 1000)
        version = sim.server.accept_desired_price(STATION, price)
        sim.server.receive_acknowledgement(STATION, version, price + 1)
        assert not _up_to_date(sim), 'seed {}'.format(seed)
        sim.server.receive_acknowledgement(STATION, version, price)
        assert _up_to_date(sim), 'seed {}'.format(seed)
