'''Verifies GASV4RDF1-55: the listing operation shows the stations not yet acknowledging their latest price.'''

import app
from nrvv_env import Simulation

KNOWN_OPS = {'set_desired_price', 'receive_acknowledgement', 'query_station_state',
             'send_update', 'send_notice', 'bind_ports'}
MAX_STEPS = 10000


def _list_op():
    names = sorted(
        n for n in dir(app)
        if 'acknowledg' in n and callable(getattr(app, n))
        and n not in KNOWN_OPS and not n.startswith('receive')
    )
    assert names, 'app has no operation listing stations not acknowledging their latest price'
    listing = [n for n in names if n.startswith('list')]
    return getattr(app, (listing or names)[0])


def _station_names(result):
    items = list(result.keys()) if isinstance(result, dict) else list(result)
    names = set()
    for item in items:
        if isinstance(item, str):
            names.add(item)
        elif isinstance(item, dict):
            names.add(item['station'])
        elif hasattr(item, 'station'):
            names.add(item.station)
        else:
            names.add(item[0])
    return names


def _listed():
    return _station_names(_list_op()())


def _expected(sim):
    unacknowledged = set()
    for station, price in sim.desired.items():
        last = sim.last_ack_price(station)
        if last is None or last != price:
            unacknowledged.add(station)
    return unacknowledged


def _assert_listing_matches(sim):
    assert _listed() & set(sim.desired) == _expected(sim)


def _run_checking_every_step(sim):
    _assert_listing_matches(sim)
    steps = 0
    while sim.step():
        _assert_listing_matches(sim)
        steps += 1
        assert steps < MAX_STEPS
    assert sim.is_quiet()


def test_listing_matches_acknowledgement_evidence_at_every_step():
    for seed in range(15):
        names = (f'p{seed}a', f'p{seed}b', f'p{seed}c')
        _run_checking_every_step(Simulation(app, seed, stations=names, calls=12))


def test_station_whose_latest_ack_matches_desired_price_is_omitted():
    for seed in range(15):
        names = (f'q{seed}a', f'q{seed}b')
        _run_checking_every_step(Simulation(app, 100 + seed, stations=names, calls=20, prices=(1, 2)))


def test_station_with_no_acknowledgement_is_listed_until_it_acknowledges_latest_price():
    a, b = 'n_a', 'n_b'
    sim = Simulation(app, 1, stations=(a, b), script=[(a, 5)])
    while a not in sim.desired:
        assert sim.step()
    assert a in _listed()
    while sim.last_ack_price(a) != 5:
        assert sim.step()
    assert a not in _listed()


def test_listing_changes_no_state():
    names = ('r_a', 'r_b', 'r_c')
    sim = Simulation(app, 7, stations=names, calls=6)
    sim.run(max_steps=8)
    before = {n: sim.query(n) for n in names}
    first = _listed()
    second = _listed()
    assert first == second
    assert first & set(sim.desired) == _expected(sim)
    assert {n: sim.query(n) for n in names} == before
