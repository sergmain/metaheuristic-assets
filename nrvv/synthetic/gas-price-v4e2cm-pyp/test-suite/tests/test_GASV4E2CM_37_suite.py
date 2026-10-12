import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3)


def _run(seed, tag, **kwargs):
    station_a = f'{tag}-{seed}-a'
    station_b = f'{tag}-{seed}-b'
    sim = Simulation(app, seed, stations=(station_a, station_b), **kwargs)
    return sim, station_a, station_b


def _settle(sim):
    assert sim.quiesce(bound=2000, idle_ticks=100), 'service did not settle after the updates'


def _last_sent_price(sim, station_id):
    sent = sim.sent_to(station_id)
    return sent[-1]['price'] if sent else None


def _publish_step(sim, station_id, price):
    '''Set the desired price, run one publishing step (one tick); return every update sent during it.'''
    mark = len(sim.sent)
    sim.set_desired_price(station_id, price)
    sim.tick()
    return sim.sent[mark:]


def _assert_change_sends_one_update(seed, tag, **kwargs):
    sim, a, b = _run(seed, tag, **kwargs)
    first = 10 + seed
    _publish_step(sim, a, first)
    _settle(sim)
    assert _last_sent_price(sim, a) == first

    sent = _publish_step(sim, a, first + 1)
    to_a = [entry for entry in sent if entry['station'] == a]
    assert len(to_a) == 1, f'expected exactly one update to {a}, got {len(to_a)}'
    assert to_a[0]['price'] == first + 1
    assert not [entry for entry in sent if entry['station'] == b]
    _settle(sim)


def _assert_unchanged_sends_nothing(seed, tag, **kwargs):
    sim, a, b = _run(seed, tag, **kwargs)
    first = 20 + seed
    _publish_step(sim, a, first)
    _settle(sim)
    assert _last_sent_price(sim, a) == first

    sent = _publish_step(sim, a, first)
    assert not [entry for entry in sent if entry['station'] == a], f'unexpected update to {a}'
    _settle(sim)


def test_changed_price_sends_exactly_one_update_to_that_station():
    for seed in SEEDS:
        _assert_change_sends_one_update(seed, 'chg', loss=0.0, outage=0.0)


def test_unchanged_price_sends_no_update_to_that_station():
    for seed in SEEDS:
        _assert_unchanged_sends_nothing(seed, 'unchg', loss=0.0, outage=0.0)


def test_changed_price_sends_one_update_under_loss_and_outage():
    for seed in SEEDS:
        _assert_change_sends_one_update(seed, 'chgl')


def test_unchanged_price_sends_no_update_under_loss_and_outage():
    for seed in SEEDS:
        _assert_unchanged_sends_nothing(seed, 'unchgl')
