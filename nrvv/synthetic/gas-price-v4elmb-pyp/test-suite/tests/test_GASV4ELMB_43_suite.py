# Test suite for GASV4ELMB-6: the service delivers the latest desired price to each
# station without changing the station's behaviour, software or display.
# Driven only through app and nrvv_env. Stations are the unmodified simulated stations.
import importlib

import app
from nrvv_env import Simulation

SEEDS = range(12)


def _run(seed, stations=4, active_ticks=60):
    # Reload app so each run starts from a fresh service state; Simulation installs its port on app.
    importlib.reload(app)
    sim = Simulation(app, seed, stations=stations, active_ticks=active_ticks)
    sim.run()
    return sim


def test_every_reachable_station_shows_latest_desired_price():
    for seed in SEEDS:
        sim = _run(seed)
        assert sim.changes, 'seed %d: no desired price was set' % seed
        assert sim.final_display_mismatches() == [], 'seed %d: stale or wrong display' % seed


def test_latest_price_shown_with_more_stations():
    for seed in range(100, 106):
        sim = _run(seed, stations=8, active_ticks=40)
        assert sim.final_display_mismatches() == [], 'seed %d: stale or wrong display' % seed


def test_service_record_matches_station_display():
    for seed in SEEDS:
        sim = _run(seed)
        for s in sim.reachable_at_end():
            view = sim.server_state(s)
            latest = sim.final_desired(s)
            assert view['desired_price'] == latest, 'seed %d station %s: service desired differs' % (seed, s)
            assert view['shown_price'] == sim.stations[s].price, 'seed %d station %s: service record differs from display' % (seed, s)
            assert sim.stations[s].price == latest, 'seed %d station %s: display differs from latest desired' % (seed, s)
            assert view['in_flight_seq'] is None, 'seed %d station %s: update still in flight after settling' % (seed, s)


def test_displayed_price_is_latest_unaltered_sent_update():
    for seed in SEEDS:
        sim = _run(seed)
        for s in sim.reachable_at_end():
            latest = sim.final_desired(s)
            if latest is None:
                assert sim.stations[s].price is None, 'seed %d station %s: shows a price never desired' % (seed, s)
                continue
            assert sim.deliveries[s], 'seed %d station %s: never received an update' % (seed, s)
            last = sim.deliveries[s][-1]
            assert last.price == latest, 'seed %d station %s: last delivered price is not the latest' % (seed, s)
            sent = [x for x in sim.sends if x.station == s and x.seq == last.seq and x.price == last.price]
            assert sent, 'seed %d station %s: delivered update was not sent unaltered' % (seed, s)
