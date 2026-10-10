'''Suite for GASV4RDF1-4: keep updating a station until its latest price is confirmed.'''

import inspect

import app
import nrvv_env


STATION = 'station-1'
OTHER_STATION = 'station-2'
PRICE = 1.499
ATTEMPTS = 4
SEEDS = (1, 2, 3, 4, 5)
MAX_CLOCK = 20000


def _server_class():
    classes = [value for value in vars(app).values()
               if inspect.isclass(value) and callable(getattr(value, 'set_desired_price', None))]
    assert len(classes) == 1, f'expected one server class in app, found {[c.__name__ for c in classes]}'
    return classes[0]


def _make_server(send_update, send_pricing_notice):
    return _server_class()(send_update, send_pricing_notice)


def _attempts(sim):
    return [update for update in sim.sent if update.station == STATION]


def _run_withholding_acks(seed):
    '''Runs one seeded simulation; acks for the first three attempts to STATION are withheld.'''
    sim = nrvv_env.Simulation(
        seed, _make_server, [STATION, OTHER_STATION],
        script=[[(STATION, PRICE)], [(OTHER_STATION, price) for price in range(1, 41)]])
    station = sim.stations[STATION]
    while not sim.quiet:
        assert sim.clock.now < MAX_CLOCK, f'seed {seed}: run did not settle'
        attempts = _attempts(sim)
        fourth = attempts[ATTEMPTS - 1].update_id if len(attempts) >= ATTEMPTS else None
        for ack in list(station.acks):
            if ack.update_id != fourth:
                station.acks.remove(ack)
        sim.step()
    return sim


def _fourth_ack(sim):
    attempts = _attempts(sim)
    assert len(attempts) >= ATTEMPTS, f'only {len(attempts)} attempts were sent'
    acks = [ack for ack in sim.delivered_acks if ack.station == STATION]
    assert [ack.update_id for ack in acks] == [attempts[ATTEMPTS - 1].update_id], \
        'the fourth attempt was not the one acknowledged'
    return acks[0]


def test_first_four_attempts_each_carry_latest_price():
    for seed in SEEDS:
        sim = _run_withholding_acks(seed)
        attempts = _attempts(sim)
        assert len(attempts) >= ATTEMPTS, f'seed {seed}: only {len(attempts)} attempts'
        assert [update.price for update in attempts[:ATTEMPTS]] == [PRICE] * ATTEMPTS, f'seed {seed}'


def test_sending_continues_until_fourth_attempt_is_acknowledged():
    for seed in SEEDS:
        sim = _run_withholding_acks(seed)
        ack = _fourth_ack(sim)
        assert ack.price == PRICE, f'seed {seed}: acknowledged price {ack.price}'


def test_no_update_sent_after_fourth_acknowledgement():
    for seed in SEEDS:
        sim = _run_withholding_acks(seed)
        ack = _fourth_ack(sim)
        later = [update for update in _attempts(sim) if update.step >= ack.step]
        assert later == [], f'seed {seed}: updates sent after the fourth acknowledgement: {later}'
