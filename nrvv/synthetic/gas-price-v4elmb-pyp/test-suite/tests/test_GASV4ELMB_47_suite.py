import importlib
from collections import defaultdict

from nrvv_env import Simulation
from nrvv_env.simulation import MAX_PRICE

SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)


def _run(seed):
    app = importlib.import_module('app')
    importlib.reload(app)
    stations = ['P%d-S%d' % (seed, i) for i in range(3)]
    sim = Simulation(app, seed, stations=stations)
    sim.run()
    return sim


def test_outbound_traffic_to_station_is_only_price_updates():
    for seed in SEEDS:
        sim = _run(seed)
        for send in sim.sends:
            assert send.station in sim.station_ids
            assert type(send.seq) is int and send.seq >= 1
            assert type(send.price) is int and 0 <= send.price <= MAX_PRICE
        sent = {(x.station, x.seq, x.price) for x in sim.sends}
        for s in sim.station_ids:
            for d in sim.deliveries[s]:
                assert (s, d.seq, d.price) in sent


def test_latest_absolute_price_is_sent_with_its_sequence_number_and_acknowledged():
    for seed in SEEDS:
        sim = _run(seed)
        for s in sim.station_ids:
            final = sim.final_desired(s)
            if final is None or not sim.reachable(s):
                continue
            sends = [x for x in sim.sends if x.station == s]
            assert sends, 'no update was sent to %s' % s
            n = max(x.seq for x in sends)
            assert all(x.price == final for x in sends if x.seq == n)
            acked = [a for a in sim.acks if a.station == s and a.seq == n and not a.dropped]
            assert acked, 'seq %d of %s was never acknowledged' % (n, s)
            assert sim.stations[s].price == final
            assert sim.server_state(s)['shown_price'] == final


def test_each_acknowledgement_carries_the_sequence_number_of_its_update():
    for seed in SEEDS:
        sim = _run(seed)
        for s in sim.station_ids:
            acks = [a for a in sim.acks if a.station == s]
            deliveries = sim.deliveries[s]
            assert [a.seq for a in acks] == [d.seq for d in deliveries]
            assert [a.produced for a in acks] == [d.tick for d in deliveries]


def test_retransmissions_reuse_the_sequence_number_and_price():
    for seed in SEEDS:
        sim = _run(seed)
        groups = defaultdict(list)
        for x in sim.sends:
            groups[(x.station, x.seq)].append(x)
        for group in groups.values():
            assert len({x.price for x in group}) == 1
            assert [x.retransmission for x in group] == [False] + [True] * (len(group) - 1)
        for s in sim.station_ids:
            seqs = [key[1] for key in groups if key[0] == s]
            assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_station_receives_only_complete_absolute_prices_from_desired_history():
    for seed in SEEDS:
        sim = _run(seed)
        for s in sim.station_ids:
            history = {p for _, p in sim.desired[s]}
            for x in sim.sends:
                if x.station == s:
                    assert x.price in history
            for d in sim.deliveries[s]:
                assert d.price in history
