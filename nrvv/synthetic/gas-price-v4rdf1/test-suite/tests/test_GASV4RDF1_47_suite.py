'''Tests for GASV4RDF1-31: confirm the latest price on ack and send one notice.'''

import inspect

import app
import nrvv_env


STATION = 'S1'
SEEDS = range(8)
MAX_STEPS = 100000


def _make_server(send_update, send_pricing_notice):
    '''Builds the app's server object from its two outbound ports.'''
    for name in dir(app):
        candidate = getattr(app, name)
        if not (inspect.isclass(candidate) and name[:1].isupper()):
            continue
        try:
            server = candidate(send_update, send_pricing_notice)
        except TypeError:
            continue
        if all(hasattr(server, method) for method in
               ('set_desired_price', 'receive_acknowledgement', 'query_station_state')):
            return server
    raise AssertionError('app has no server class taking the outbound ports')


def _state_field(state, name):
    '''Reads the confirmed, desired or outstanding field of a QueryStationState result.'''
    if isinstance(state, dict):
        return next(value for key, value in state.items() if name in str(key).lower())
    attrs = [attr for attr in dir(state) if name in attr.lower() and not attr.startswith('_')]
    if attrs:
        return getattr(state, attrs[0])
    order = ('confirmed', 'desired', 'outstanding')
    return tuple(state)[order.index(name)]


def _notices(sim, station, price):
    return [n for n in sim.pricing.notices if n.station == station and n.price == price]


def _single_price_run(seed, price):
    sim = nrvv_env.Simulation(seed, _make_server, [STATION],
                              script=[[(STATION, price)]], clients=1)
    sim.run(max_steps=MAX_STEPS)
    return sim


def test_latest_price_confirmed_on_ack_and_notified_once():
    for seed in SEEDS:
        price = 7 + seed
        sim = _single_price_run(seed, price)
        assert sim.latest_desired(STATION) == price
        acks = [ack for ack in sim.delivered_acks if ack.station == STATION and ack.price == price]
        assert acks, f'seed {seed}: no acknowledgement showing the latest price'
        assert _state_field(sim.query(STATION), 'confirmed') == price
        notices = _notices(sim, STATION, price)
        assert len(notices) == 1, f'seed {seed}: {len(notices)} notices'
        # Logical time is a step counter, so a notice sent in the step of the ack takes no elapsed time.
        assert notices[0].step == acks[0].step


def test_repeated_acknowledgement_sends_no_second_notice():
    for seed in SEEDS:
        price = 20 + seed
        sim = _single_price_run(seed, price)
        before = _notices(sim, STATION, price)
        assert len(before) == 1, f'seed {seed}: {len(before)} notices before redelivery'
        sim.server.receive_acknowledgement(STATION, price)
        sim.server.receive_acknowledgement(STATION, price)
        assert _notices(sim, STATION, price) == before
        assert _state_field(sim.query(STATION), 'confirmed') == price


def test_older_price_ack_is_not_confirmed_and_sends_no_notice():
    for seed in SEEDS:
        older, latest = 10 + seed, 50 + seed
        sim = nrvv_env.Simulation(seed, _make_server, [STATION],
                                  script=[[(STATION, older), (STATION, latest)]], clients=1)
        sim.run(max_steps=MAX_STEPS)
        assert sim.latest_desired(STATION) == latest
        assert _state_field(sim.query(STATION), 'confirmed') == latest
        notices_before = list(sim.pricing.notices)
        sim.server.receive_acknowledgement(STATION, older)
        assert _state_field(sim.query(STATION), 'confirmed') == latest
        assert sim.pricing.notices == notices_before


def test_every_notice_matches_latest_price_ack_at_its_step():
    for seed in SEEDS:
        sim = nrvv_env.Simulation(seed, _make_server, ['S1', 'S2', 'S3'], clients=3, calls=8)
        sim.run(max_steps=MAX_STEPS)
        for notice in sim.pricing.notices:
            assert sim.desired_at(notice.station, notice.step) == notice.price
            assert any(ack.station == notice.station and ack.price == notice.price
                       and ack.step == notice.step for ack in sim.delivered_acks)
