'''Tests for GASV4RDF1-12: send the latest desired price after each change, when needed.'''

import app
from nrvv_env import Simulation

STATION = 'S'
SEEDS = range(8)


def _make_server(send_update, send_pricing_notice):
    for name in dir(app):
        candidate = getattr(app, name)
        if isinstance(candidate, type) and hasattr(candidate, 'set_desired_price'):
            return candidate(send_update, send_pricing_notice)
    raise AssertionError('app has no server class offering set_desired_price')


def _state(sim, station=STATION):
    confirmed, desired, outstanding = sim.query(station)
    return confirmed, desired, outstanding


def _start():
    sim = Simulation(1, _make_server, [STATION], script=[[]])
    sim.server.set_desired_price(STATION, 100)
    if _state(sim)[2] > 0:
        sim.server.receive_acknowledgement(STATION, 100)
    assert _state(sim) == (100, 100, 0)
    return sim


def test_gasv4rdf1_12_change_to_105_sends_one_update_and_appends_it():
    sim = _start()
    mark = len(sim.sent)
    before = _state(sim)[2]
    sim.server.set_desired_price(STATION, 105)
    assert [u.price for u in sim.sent[mark:]] == [105]
    assert sim.sent[-1].station == STATION
    assert _state(sim) == (100, 105, before + 1)


def test_gasv4rdf1_12_change_to_110_while_105_outstanding_sends_110_and_appends_it():
    sim = _start()
    sim.server.set_desired_price(STATION, 105)
    mark = len(sim.sent)
    before = _state(sim)[2]
    sim.server.set_desired_price(STATION, 110)
    assert [u.price for u in sim.sent[mark:]] == [110]
    assert _state(sim) == (100, 110, before + 1)


def test_gasv4rdf1_12_change_to_105_while_105_outstanding_sends_nothing():
    sim = _start()
    sim.server.set_desired_price(STATION, 105)
    sim.server.set_desired_price(STATION, 110)
    mark = len(sim.sent)
    before = _state(sim)[2]
    sim.server.set_desired_price(STATION, 105)
    assert len(sim.sent) == mark
    assert _state(sim) == (100, 105, before)


def test_gasv4rdf1_12_ack_while_desired_not_outstanding_sends_desired_once():
    sim = _start()
    sim.server.set_desired_price(STATION, 105)
    sim.server.set_desired_price(STATION, 110)
    sim.server.set_desired_price(STATION, 105)
    mark = len(sim.sent)
    sim.server.receive_acknowledgement(STATION, 110)
    assert [u.price for u in sim.sent[mark:]] == [105]
    confirmed, desired, _ = _state(sim)
    assert confirmed == 110
    assert desired == 105


def _run(seed):
    sim = Simulation(seed, _make_server, ['A', 'B'], clients=3, calls=10)
    sim.run(max_steps=10000)
    return sim


def _confirmed_at(sim, station, step):
    price = None
    for ack in sim.delivered_acks:
        if ack.step > step:
            break
        if ack.station == station:
            price = ack.price
    return price


def test_gasv4rdf1_12_random_runs_send_desired_price_only_when_confirmed_differs_and_not_outstanding():
    for seed in SEEDS:
        sim = _run(seed)
        acked_at = {ack.update_id: ack.step for ack in sim.delivered_acks}
        for upd in sim.sent:
            assert upd.price == sim.desired_at(upd.station, upd.step), (seed, upd)
            assert upd.price != _confirmed_at(sim, upd.station, upd.step), (seed, upd)
            for earlier in sim.sent:
                if (earlier.update_id < upd.update_id and earlier.station == upd.station
                        and earlier.price == upd.price):
                    removed = acked_at.get(earlier.update_id)
                    assert removed is not None and removed <= upd.step, (seed, earlier, upd)


def test_gasv4rdf1_12_quiet_run_ends_with_confirmed_price_equal_to_desired():
    for seed in SEEDS:
        sim = _run(seed)
        for station in sim.station_names:
            desired = sim.latest_desired(station)
            if desired is None:
                continue
            assert _state(sim, station) == (desired, desired, 0), (seed, station)
