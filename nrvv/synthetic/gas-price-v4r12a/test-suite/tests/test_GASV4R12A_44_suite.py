'''Tests for GASV4R12A-15: resend rule - no in-flight update for the desired version.'''
import app
from nrvv_env import Simulation

STATION = 's1'
SEEDS = (1, 2, 3)
OLD_PRICE = 100
MID_PRICE = 200
NEW_PRICE = 300


def _make_sim(seed):
    sim = Simulation(seed, stations=(STATION,), stop_tick=50, fault_window=(0, 0),
                     max_delay=3, loss=0.0, change_rate=0.0)
    sim.attach(lambda send: app.Server(send_update=send))
    return sim


def _sends(sim, tick):
    return [r for r in sim.sends if r.station == STATION and r.tick == tick]


def _in_flight_versions(sim):
    return [u.version for u in sim.in_flight_updates() if u.station == STATION]


def _acknowledge(sim, price):
    '''Drive the station to acknowledge `price`, then drain the transport.'''
    sim.set_reachable(STATION, True)
    sim.source_schedule = {sim.now + 1: [(STATION, price)]}
    for _ in range(100):
        sim.step()
        if any(a.displayed == price for a in sim.acks):
            break
    else:
        raise AssertionError('no acknowledgement of {} within 100 ticks'.format(price))
    for _ in range(100):
        if not sim.in_flight():
            return
        sim.step()
    raise AssertionError('transport did not drain')


def test_three_phase_resend_rule_on_one_station():
    for seed in SEEDS:
        sim = _make_sim(seed)
        _acknowledge(sim, OLD_PRICE)
        start = sim.now

        # Phase 1: an unacknowledged older version is in flight; the desired price
        # differs from the acknowledged price and has no in-flight record yet.
        sim.set_reachable(STATION, False)
        sim.source_schedule = {start + 1: [(STATION, MID_PRICE)],
                               start + 2: [(STATION, NEW_PRICE)]}
        sim.step()
        older = _sends(sim, start + 1)
        assert len(older) == 1 and older[0].price == MID_PRICE, (seed, older)
        older_version = older[0].version
        assert older_version in _in_flight_versions(sim), seed
        sim.step()
        sent = _sends(sim, start + 2)
        assert len(sent) == 1, ('seed {}: expected exactly one update, got {}'.format(seed, sent))
        assert sent[0].price == NEW_PRICE, (seed, sent[0])
        assert sent[0].version != older_version, seed
        new_version = sent[0].version

        # Phase 2: same price difference, now with an in-flight record for the desired version.
        assert new_version in _in_flight_versions(sim), seed
        sim.step()
        assert _sends(sim, start + 3) == [], seed

        # Phase 3: let acknowledgements arrive so the acknowledged price equals the desired
        # price and nothing is in flight; a further send trigger must send nothing.
        sim.set_reachable(STATION, True)
        for _ in range(100):
            if not sim.in_flight():
                break
            sim.step()
        else:
            raise AssertionError('seed {}: transport did not drain'.format(seed))
        assert sim.stations[STATION].displayed == NEW_PRICE, seed
        assert any(a.version == new_version and a.displayed == NEW_PRICE for a in sim.acks), seed
        mark = len(sim.sends)
        sim.step()
        assert [r for r in sim.sends[mark:] if r.station == STATION] == [], seed


def test_no_resend_while_current_version_in_flight():
    for seed in SEEDS:
        sim = _make_sim(seed)
        _acknowledge(sim, OLD_PRICE)
        start = sim.now
        sim.set_reachable(STATION, False)
        sim.source_schedule = {start + 1: [(STATION, NEW_PRICE)]}
        sim.step()
        sent = _sends(sim, start + 1)
        assert len(sent) == 1 and sent[0].price == NEW_PRICE, (seed, sent)
        assert sent[0].version in _in_flight_versions(sim), seed
        sim.step()
        assert _sends(sim, start + 2) == [], seed


def test_no_resend_when_acked_price_matches_desired():
    for seed in SEEDS:
        sim = _make_sim(seed)
        _acknowledge(sim, MID_PRICE)
        assert sim.stations[STATION].displayed == MID_PRICE, seed
        assert not sim.in_flight(), seed
        mark = len(sim.sends)
        for _ in range(2):
            sim.step()
        assert [r for r in sim.sends[mark:] if r.station == STATION] == [], seed
