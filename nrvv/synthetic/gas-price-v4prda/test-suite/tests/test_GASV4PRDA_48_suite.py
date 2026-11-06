"""GASV4PRDA-48: after a newer price P2 is sent to a station, no update carrying the superseded price P1 is received (GASV4PRDA-11)."""

import app
from nrvv_env import Simulation

STATION = "S1"
P1 = 10  # older desired price
P2 = 20  # newer desired price, sent only after P1 is acknowledged
SEEDS = (1, 2, 3, 4, 5)
MAX_STEPS_PER_PRICE = 1000
OBSERVE_SECONDS = 300


def _simulation(seed, **options):
    # No random central changes: the test issues the desired prices itself.
    return Simulation(seed, app, stations=[STATION], change_rate=0.0, **options)


def _acknowledged(sim, price):
    sends = [c for c in sim.send_calls if c.station_id == STATION and c.price == price]
    if not sends:
        return False
    seq = sends[-1].sequence_number
    return any(a.station_id == STATION and a.sequence_number == seq for a in sim.ack_calls)


def _send_and_settle(sim, price):
    """Issue a desired price, then step until it is acknowledged and no message is in flight."""
    # The server's operations are reached through the simulation's bound server object.
    sim._server.desired_price_change(STATION, price)
    for _ in range(MAX_STEPS_PER_PRICE):
        if _acknowledged(sim, price) and sim.in_flight() == 0:
            return
        sim.step()
    raise AssertionError(
        f"seed {sim.seed}: price {price} not acknowledged within {MAX_STEPS_PER_PRICE} seconds"
    )


def _check_no_superseded_after_newer(sim):
    _send_and_settle(sim, P1)  # station has acknowledged every copy of P1
    _send_and_settle(sim, P2)  # newer price P2 is sent and acknowledged
    sim.run(OBSERVE_SECONDS)  # record everything the station receives, including retransmissions

    received = sim.stations[STATION].received  # (time, sequence_number, price) per copy
    p2_indexes = [i for i, (_, _, price) in enumerate(received) if price == P2]
    assert p2_indexes, f"seed {sim.seed}: station never received the newer price P2"
    later_p1 = [entry for entry in received[p2_indexes[0] + 1:] if entry[2] == P1]
    assert not later_p1, f"seed {sim.seed}: superseded price P1 received after P2: {later_p1}"


def test_no_superseded_price_after_newer_one_with_transport_faults():
    # Losses and duplicate copies are on (default), stations never go out of reach.
    for seed in SEEDS:
        _check_no_superseded_after_newer(_simulation(seed, outages=False))


def test_no_superseded_price_after_newer_one_with_station_outages():
    # Station outages on (default): updates sent while unreachable are dropped and retransmitted later.
    for seed in SEEDS:
        _check_no_superseded_after_newer(_simulation(seed))
