import inspect

import app
from nrvv_env import Simulation

STATIONS = ('station-A', 'station-B', 'station-C')
SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)


def _make_server():
    for name in ('PriceServer', 'Server', 'PriceDispatcher', 'Dispatcher'):
        cls = getattr(app, name, None)
        if inspect.isclass(cls):
            return cls()
    return app


def _run(seed):
    sim = Simulation(seed, STATIONS, changes_per_station=(1, 4))
    sim.bind(_make_server())
    sim.run_to_end()
    return sim


def test_update_content_is_station_and_price_only():
    for seed in SEEDS:
        # The outbound port takes exactly (station, price); any version, sequence
        # or duplicate-detection argument makes the server raise during the run.
        sim = _run(seed)
        assert sim.sends, f'seed {seed}: no update was dispatched'
        for record in sim.sends:
            assert record.station in STATIONS
            chosen = {c.price for c in sim.changes if c.station == record.station}
            assert record.price in chosen


def test_each_station_final_price_is_dispatched_without_versioning():
    for seed in SEEDS:
        sim = _run(seed)
        counts = sim.send_counts()
        for station in STATIONS:
            assert counts[station] >= 1, f'seed {seed}: {station} got no update'
            sent_prices = {r.price for r in sim.sends if r.station == station}
            assert sim.reference_final_prices[station] in sent_prices


def test_station_only_acknowledgement_is_accepted():
    for seed in SEEDS:
        # Acknowledgements reach the server as acknowledgement_received(station) only;
        # a rejection or a request for more data would surface as an exception here.
        sim = _run(seed)
        assert sim.acknowledgements, f'seed {seed}: no acknowledgement was returned'
        assert len(sim.acknowledgements) == len(sim.deliveries)
        assert sim.unacknowledged_sends() == []
        for _, station in sim.acknowledgements:
            assert station in STATIONS
