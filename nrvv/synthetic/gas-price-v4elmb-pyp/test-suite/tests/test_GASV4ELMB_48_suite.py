"""GASV4ELMB-48: a busy station keeps its in-flight update; the next update carries the latest desired price."""
import app
from nrvv_env import Simulation

P1, P2, P3 = 10, 20, 30
SEEDS = range(20)
RUN_TICKS = 300


def _run(tag, seed):
    station = '%s%d' % (tag, seed)
    sim = Simulation(app, seed, stations=[station], active_ticks=1)
    sim.outages = {station: []}
    # Tick 1: desired price becomes P1 and the update for P1 is sent.
    # Tick 2: desired price becomes P2, then P3, while the update for P1 is still unacknowledged
    # (no copy of it can be delivered, let alone acknowledged, before the end of tick 2).
    sim._script_by_tick = {1: [(station, P1)], 2: [(station, P2), (station, P3)]}
    for _ in range(RUN_TICKS):
        sim.step()
    return sim, station


def _sends(sim, station):
    return [s for s in sim.sends if s.station == station]


def _first_ack_tick(sim, station, seq):
    arrivals = [a.arrived for a in sim.acks if a.station == station and a.seq == seq and not a.dropped]
    assert arrivals, 'no acknowledgement of seq %d arrived' % seq
    return min(arrivals)


def _shown_by_station(sim, station):
    assert sim.deliveries[station], 'station received no update'
    return max(sim.deliveries[station], key=lambda d: d.seq).price


def test_no_new_update_sent_while_first_update_unacknowledged():
    for seed in SEEDS:
        sim, station = _run('W', seed)
        busy = [c for c in sim.changes if c.station == station and c.tick == 2]
        assert [c.price for c in busy] == [P2, P3], seed
        assert all(c.view_before['in_flight_seq'] == 1 for c in busy), seed
        ack_tick = _first_ack_tick(sim, station, 1)
        window = [s for s in _sends(sim, station) if 2 <= s.tick < ack_tick]
        for s in window:
            # Only a retransmission of the outstanding update may go out; no new sequence number or price.
            assert s.seq == 1 and s.price == P1 and s.retransmission, (seed, s)


def test_next_update_after_ack_carries_desired_price_at_send_time():
    for seed in SEEDS:
        sim, station = _run('N', seed)
        ack_tick = _first_ack_tick(sim, station, 1)
        assert not [s for s in sim.sends if s.price == P2], (seed, 'superseded price P2 was sent')
        later = [s for s in _sends(sim, station) if s.seq > 1]
        assert later, (seed, 'no update sent after the acknowledgement')
        nxt = later[0]
        assert nxt.seq == 2, (seed, nxt)
        assert nxt.tick >= ack_tick, (seed, nxt)
        assert nxt.price == P3, (seed, nxt)
        assert nxt.desired == P3, (seed, nxt)


def test_after_final_ack_no_update_and_shown_price_is_latest_desired():
    for seed in SEEDS:
        sim, station = _run('F', seed)
        sends = _sends(sim, station)
        final_seq = max(s.seq for s in sends)
        assert final_seq == 2, (seed, final_seq)
        final_ack = _first_ack_tick(sim, station, final_seq)
        assert all(s.tick <= final_ack for s in sends), (seed, 'update sent after final acknowledgement')
        assert [s.price for s in sends if s.seq == final_seq][-1] == P3, seed
        state = sim.server_state(station)
        assert state['desired_price'] == P3, (seed, state)
        assert state['in_flight_seq'] is None, (seed, state)
        assert state['shown_price'] == P3, (seed, state)
        assert _shown_by_station(sim, station) == P3, seed
