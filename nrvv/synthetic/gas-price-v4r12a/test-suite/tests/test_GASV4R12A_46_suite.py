'''Requirement GASV4R12A-19: convergence uses only update and acknowledgement messages.'''
import collections

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)


def _cycle(seed):
    sim = Simulation(seed)
    sim.attach(lambda send: app.Server(send_update=send))
    report = sim.assert_converged()
    return sim, report


def test_server_sends_only_update_messages():
    for seed in SEEDS:
        sim, _ = _cycle(seed)
        assert sim.changes, 'seed {}: no desired price change was made'.format(seed)
        assert sim.sends, 'seed {}: server sent no update'.format(seed)
        for send in sim.sends:
            assert send.station in sim.stations
            assert send.price is not None
            assert send.version is not None


def test_station_returns_only_acknowledgements_matching_updates():
    for seed in SEEDS:
        sim, _ = _cycle(seed)
        delivered = collections.Counter(
            (s.station, s.version, s.price) for s in sim.sends if s.delivered_tick is not None)
        returned = collections.Counter(
            (a.station, a.version, a.displayed) for a in sim.acks + sim.in_flight_acks())
        assert returned == delivered, 'seed {}: acknowledgements do not match delivered updates'.format(seed)


def test_no_configuration_or_negotiation_traffic():
    for seed in SEEDS:
        sim, _ = _cycle(seed)
        first_change = min(c.tick for c in sim.changes)
        assert min(s.tick for s in sim.sends) >= first_change
        for sid, station in sim.stations.items():
            prices = {s.price for s in sim.sends
                      if s.station == sid and s.delivered_tick is not None}
            if prices:
                assert station.displayed in prices
            else:
                assert station.displayed is None


def test_full_cycle_converges_using_only_updates_and_acks():
    for seed in SEEDS:
        sim, report = _cycle(seed)
        assert report.converged, 'seed {}: {}'.format(seed, report.failures)
        assert report.failures == []
        for sid, price in sim.latest_desired().items():
            assert sim.stations[sid].displayed == price
        assert all(state['up_to_date'] for state in report.stations.values())


def test_lost_updates_are_recovered_by_resending_updates():
    lost_total = 0
    for seed in SEEDS:
        sim, report = _cycle(seed)
        lost_total += sum(1 for s in sim.sends if s.lost)
        assert report.converged, 'seed {}: {}'.format(seed, report.failures)
    assert lost_total > 0, 'no update was lost, so the recovery path was not exercised'
