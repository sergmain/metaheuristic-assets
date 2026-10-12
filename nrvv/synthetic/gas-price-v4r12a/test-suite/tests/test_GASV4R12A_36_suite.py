'''Tests for GASV4R12A-4: resend the latest desired price to stations not confirmed on it.'''
import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3)
OLD_PRICE = 500
NEW_PRICE = 600


def _make_sim(seed, schedule, stop_tick, fault_window=(0, 0), loss=0.0):
    sim = Simulation(seed, stations=('s1',), stop_tick=stop_tick, fault_window=fault_window,
                     max_delay=1, loss=loss, change_rate=0.0)
    sim.source_schedule = schedule
    sim.attach(lambda send: app.Server(send_update=send))
    return sim


def _sends_to(sim, price=None, after_tick=0):
    return [s for s in sim.sends
            if s.station == 's1' and s.tick > after_tick and (price is None or s.price == price)]


def _wait_for_resend(sim, price, after_tick, budget=300):
    while sim.now < budget:
        found = _sends_to(sim, price, after_tick)
        if found:
            return found[0]
        sim.step()
    return None


def test_resends_latest_price_to_station_with_stale_acknowledgement():
    for seed in SEEDS:
        # 500 is applied and acknowledged; 600 is accepted while its transmission is lost,
        # so the station stays on 500 and no unacknowledged update carrying 600 is in flight.
        sim = _make_sim(seed, {1: [('s1', OLD_PRICE)], 4: [('s1', NEW_PRICE)]}, stop_tick=4,
                        fault_window=(4, 5), loss=1.0)
        sim.run(4)
        assert sim.stations['s1'].displayed == OLD_PRICE
        assert sim.latest_desired()['s1'] == NEW_PRICE
        assert not [u for u in sim.in_flight_updates() if u.price == NEW_PRICE]
        assert [s for s in _sends_to(sim, NEW_PRICE) if s.lost]
        resend = _wait_for_resend(sim, NEW_PRICE, after_tick=4)
        assert resend is not None, 'latest desired price was never resent (seed {})'.format(seed)
        assert not resend.lost
        assert not _sends_to(sim, OLD_PRICE, after_tick=4)
        while sim.now < 320 and sim.stations['s1'].displayed != NEW_PRICE:
            sim.step()
        assert sim.stations['s1'].displayed == NEW_PRICE


def test_resends_latest_price_to_station_never_acknowledged():
    for seed in SEEDS:
        # The only update ever sent is lost, so the station has never displayed anything.
        sim = _make_sim(seed, {1: [('s1', NEW_PRICE)]}, stop_tick=1, fault_window=(1, 2), loss=1.0)
        sim.run(1)
        assert sim.stations['s1'].displayed is None
        assert not sim.acks
        assert [s for s in _sends_to(sim, NEW_PRICE) if s.lost]
        resend = _wait_for_resend(sim, NEW_PRICE, after_tick=1)
        assert resend is not None, 'latest desired price was never resent (seed {})'.format(seed)
        assert not resend.lost
        while sim.now < 320 and sim.stations['s1'].displayed != NEW_PRICE:
            sim.step()
        assert sim.stations['s1'].displayed == NEW_PRICE


def test_no_update_when_acknowledged_price_equals_latest_desired():
    for seed in SEEDS:
        sim = _make_sim(seed, {1: [('s1', OLD_PRICE)]}, stop_tick=3)
        sim.run_until_idle()
        assert sim.acks[-1].displayed == OLD_PRICE
        assert sim.latest_desired()['s1'] == OLD_PRICE
        sent_before = len(_sends_to(sim))
        sim.run(5)
        assert len(_sends_to(sim)) == sent_before


def test_no_update_while_latest_price_is_unacknowledged_in_flight():
    for seed in SEEDS:
        sim = _make_sim(seed, {1: [('s1', OLD_PRICE)]}, stop_tick=3)
        # Tick 2: the update has been applied, its acknowledgement is still in flight.
        sim.run(2)
        assert sim.stations['s1'].displayed == OLD_PRICE
        assert not sim.acks
        assert [a for a in sim.in_flight_acks() if a.displayed == OLD_PRICE]
        sent_before = len(_sends_to(sim))
        # Tick 3: the resend step runs before the acknowledgement is delivered.
        sim.step()
        assert sim.acks and sim.acks[-1].delivered_tick == 3
        assert len(_sends_to(sim)) == sent_before
