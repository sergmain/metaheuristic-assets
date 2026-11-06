# Criterion GASV4ELMB-37 (requirement GASV4ELMB-20): the pending state keeps only the latest desired price.
import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)
BUSY_LIMIT = 200
SETTLE_LIMIT = 5000
_RUNS = [0]


def _new_run(seed):
    _RUNS[0] += 1
    station = 'N%d_%d' % (seed, _RUNS[0])
    sim = Simulation(app, seed, stations=[station])
    sim.script = []
    sim._script_by_tick = {}
    sim.outages = {station: []}
    sim.tick = _RUNS[0] * 1000000
    return sim, station


def _run_to_busy(sim, station):
    sim._central_change(sim.tick, station, 0)
    for _ in range(BUSY_LIMIT):
        if sim.server_state(station)['in_flight_seq'] is not None:
            return
        sim.step()
    raise AssertionError('station never became busy (seed %r)' % sim.seed)


def _change_while_busy_and_settle(seed):
    sim, station = _new_run(seed)
    _run_to_busy(sim, station)
    old_seq = sim.server_state(station)['in_flight_seq']
    change_tick = sim.tick
    for price in ('A', 'B', 'C'):
        sim._central_change(change_tick, station, price)
    sim.last_change_tick = change_tick
    sim.run(max_ticks=change_tick + SETTLE_LIMIT)
    return sim, station, old_seq, change_tick


def test_coalesced_changes_send_only_latest_price():
    for seed in SEEDS:
        sim, station, old_seq, change_tick = _change_while_busy_and_settle(seed)
        prices = [s.price for s in sim.sends if s.station == station]
        assert 'A' not in prices and 'B' not in prices, (seed, prices)
        new = [s for s in sim.sends if s.station == station and s.tick >= change_tick and s.seq > old_seq]
        assert new, (seed, 'no update sent after the station became free')
        assert len({(s.seq, s.price) for s in new}) == 1, (seed, [(s.seq, s.price) for s in new])
        assert all(s.price == 'C' for s in new), (seed, [s.price for s in new])
        assert all(s.desired == 'C' for s in new), (seed, [s.desired for s in new])
        assert sim.final_display_mismatches() == [], (seed, sim.final_display_mismatches())
