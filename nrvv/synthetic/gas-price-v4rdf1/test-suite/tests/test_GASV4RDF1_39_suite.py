'''Suite for GASV4RDF1-30: notify the pricing team within one minute that a station holds a new price.'''

import app
import nrvv_env

ONE_MINUTE = 60
STATIONS = ['S1', 'S2', 'S3']
SEEDS = range(1, 21)


def _make_server(send_update, send_pricing_notice):
    factories = [getattr(app, name) for name in ('create_server', 'make_server', 'build_server')
                 if callable(getattr(app, name, None))]
    factories += [value for name, value in vars(app).items()
                  if name[:1].isupper() and isinstance(value, type) and value.__module__ == app.__name__]
    for factory in factories:
        try:
            server = factory(send_update, send_pricing_notice)
        except TypeError:
            continue
        if all(callable(getattr(server, op, None))
               for op in ('set_desired_price', 'receive_acknowledgement', 'query_station_state')):
            return server
    raise AssertionError('app does not provide a server built from the two outbound ports')


def _acks_showing_latest_price(sim):
    '''Delivered acknowledgements whose price is the latest desired price for the station at receipt.'''
    return [ack for ack in sim.delivered_acks
            if ack.price == sim.desired_at(ack.station, ack.step)]


def _assert_pricing_notified_in_time(sim, seed):
    acks = _acks_showing_latest_price(sim)
    for ack in acks:
        in_time = [n for n in sim.pricing.notices
                   if n.station == ack.station and n.price == ack.price
                   and ack.step <= n.step <= ack.step + ONE_MINUTE]
        assert in_time, (f'seed {seed}: no pricing notice for {ack.station} at {ack.price} '
                         f'within {ONE_MINUTE} steps after the ack at step {ack.step}')
    return len(acks)


def test_latest_price_ack_notifies_pricing_team_within_one_minute():
    checked = 0
    for seed in SEEDS:
        sim = nrvv_env.Simulation(seed, _make_server, STATIONS)
        sim.run(max_steps=20000)
        checked += _assert_pricing_notified_in_time(sim, seed)
    assert checked > 0


def test_scripted_single_price_notice_names_station_and_confirmed_price():
    sim = nrvv_env.Simulation(1, _make_server, ['S1'], script=[[('S1', 7)]])
    sim.run(max_steps=1000)
    assert _assert_pricing_notified_in_time(sim, 1) == 1
    assert any(n.station == 'S1' and n.price == 7 for n in sim.pricing.notices)


def test_notice_within_one_minute_when_many_calls_queue_on_one_station():
    script = [[('S1', p) for p in range(1, 26)], [('S1', p) for p in range(26, 51)]]
    checked = 0
    for seed in range(1, 11):
        sim = nrvv_env.Simulation(seed, _make_server, ['S1'], script=script)
        sim.run(max_steps=20000)
        checked += _assert_pricing_notified_in_time(sim, seed)
    assert checked > 0


def test_notice_within_one_minute_under_heavier_load_on_five_stations():
    stations = ['S1', 'S2', 'S3', 'S4', 'S5']
    checked = 0
    for seed in range(21, 31):
        sim = nrvv_env.Simulation(seed, _make_server, stations, clients=5, calls=30)
        sim.run(max_steps=50000)
        checked += _assert_pricing_notified_in_time(sim, seed)
    assert checked > 0
