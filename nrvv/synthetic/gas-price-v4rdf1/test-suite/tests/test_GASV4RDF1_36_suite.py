import app
from nrvv_env import Simulation

P = 500
Q = 700
SEEDS = range(50)


def _confirmed_before(sim, station, step):
    # confirmed price the server holds just before the given step: the last acknowledgement that arrived earlier
    price = None
    for ack in sim.ack_log:
        if ack.step >= step:
            break
        if ack.station == station:
            price = ack.price
    return price


def _run_script(seed, script, stations=('S1',)):
    sim = Simulation(app, seed, stations=stations, script=script)
    sim.run(max_steps=10000)
    assert sim.is_quiet()
    return sim


def _updates_sent_while_confirmed(sim, station):
    # an update whose desired price equals the confirmed price at the moment it was sent
    return [s for s in sim.sent_log
            if s.station == station and s.desired == _confirmed_before(sim, station, s.step)]


def _calls_at_confirmed_price(sim, station, price):
    return sum(1 for c in sim.call_log
               if c.station == station and c.price == price
               and _confirmed_before(sim, station, c.step) == price)


def test_no_update_sent_when_desired_equals_confirmed_price():
    covered = 0
    for seed in SEEDS:
        sim = _run_script(seed, [('S1', P), ('S1', P), ('S1', P)])
        assert _updates_sent_while_confirmed(sim, 'S1') == []
        assert sim.last_ack_price('S1') == P
        covered += _calls_at_confirmed_price(sim, 'S1', P)
    assert covered > 0


def test_no_update_sent_after_desired_change_back_to_confirmed_price():
    covered = 0
    for seed in SEEDS:
        sim = _run_script(seed, [('S1', P), ('S1', Q), ('S1', P)])
        assert _updates_sent_while_confirmed(sim, 'S1') == []
        assert sim.last_ack_price('S1') == P
        covered += _calls_at_confirmed_price(sim, 'S1', P)
    assert covered > 0


def test_no_update_sent_to_confirmed_station_while_other_station_changes():
    covered = 0
    for seed in SEEDS:
        sim = _run_script(seed, [('S1', P), ('S2', Q), ('S1', P), ('S1', P), ('S2', Q)], stations=('S1', 'S2'))
        assert _updates_sent_while_confirmed(sim, 'S1') == []
        assert _updates_sent_while_confirmed(sim, 'S2') == []
        covered += _calls_at_confirmed_price(sim, 'S1', P)
    assert covered > 0
