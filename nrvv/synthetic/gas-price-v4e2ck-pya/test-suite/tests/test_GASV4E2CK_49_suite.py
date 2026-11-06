"""GASV4E2CK-49: acknowledgements from a station are matched to the oldest pending update (GASV4E2CK-7)."""

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3)
PRICE_A = 3
PRICE_B = 7
PRICE_C = 5


def _start(seed):
    # Downlink loss 1.0: no station receives an update, so the only acknowledgements
    # are the ones the test delivers through the server's ReceiveAck port.
    return Simulation(seed, app, stations=['S1', 'S2'],
                      changes=[(1, 'S1', PRICE_A), (1, 'S1', PRICE_B), (1, 'S2', PRICE_C)],
                      loss_downlink=1.0, loss_uplink=0.0)


def _sent_to(sim, station, after=0):
    return [tx.price for tx in sim.transmissions if tx.station == station and tx.sent_at > after]


def test_first_ack_from_station_clears_oldest_update():
    for seed in SEEDS:
        sim = _start(seed)
        sim.run(1)
        assert _sent_to(sim, 'S1') == [PRICE_A, PRICE_B]
        assert _sent_to(sim, 'S2') == [PRICE_C]
        assert sim.outstanding('S1') == 2
        assert sim.outstanding('S2') == 1

        sim.server.receive_ack('S1')
        assert sim.outstanding('S1') == 1
        assert sim.outstanding('S2') == 1

        # Only B (the later update to S1) is still unacknowledged, so it is the one retransmitted at t=31.
        sim.run(30)
        assert _sent_to(sim, 'S1', after=1) == [PRICE_B]
        assert _sent_to(sim, 'S2', after=1) == [PRICE_C]


def test_second_ack_from_station_clears_remaining_update():
    for seed in SEEDS:
        sim = _start(seed)
        sim.run(1)

        sim.server.receive_ack('S1')
        sim.server.receive_ack('S1')
        assert sim.outstanding('S1') == 0
        assert sim.outstanding('S2') == 1

        # S1 has nothing left to retransmit; C to S2 is still unacknowledged.
        sim.run(30)
        assert _sent_to(sim, 'S1', after=1) == []
        assert _sent_to(sim, 'S2', after=1) == [PRICE_C]
