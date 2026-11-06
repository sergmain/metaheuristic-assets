import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)


def _up_to_date(status):
    for name in ('up_to_date', 'up_to_date_flag', 'is_up_to_date'):
        if isinstance(status, dict) and name in status:
            return bool(status[name])
        if hasattr(status, name):
            return bool(getattr(status, name))
    raise AssertionError('status has no up-to-date flag: {!r}'.format(status))


def _new_sim(seed):
    sim = Simulation(seed, stations=('s1',), fault_window=(0, 0), max_delay=1,
                     loss=0.0, change_rate=0.0)
    sim.attach(lambda send: app.Server(send_update=send))
    sim.set_reachable('s1', False)
    return sim


def _run_until_sent(sim, price, max_ticks=20):
    for _ in range(max_ticks):
        found = [s for s in sim.sends if s.price == price]
        if found:
            return found[0].version
        sim.step()
    raise AssertionError('no update priced {!r} was sent'.format(price))


def test_up_to_date_only_after_ack_for_latest_price():
    for seed in SEEDS:
        sim = _new_sim(seed)
        server = sim.server
        server.accept_desired_price('s1', '1.50')
        v1 = _run_until_sent(sim, '1.50')
        server.accept_desired_price('s1', '1.60')
        v2 = _run_until_sent(sim, '1.60')
        assert v1 != v2
        server.receive_acknowledgement('s1', v1, sim.stations['s1'].apply('1.50'))
        assert not _up_to_date(server.query_station_status('s1')), 'seed {}'.format(seed)
        server.receive_acknowledgement('s1', v2, sim.stations['s1'].apply('1.60'))
        assert _up_to_date(server.query_station_status('s1')), 'seed {}'.format(seed)


def test_not_up_to_date_without_any_ack():
    for seed in SEEDS:
        sim = _new_sim(seed)
        sim.server.accept_desired_price('s1', '1.50')
        sim.run(5)
        assert not _up_to_date(sim.server.query_station_status('s1')), 'seed {}'.format(seed)
