# GASV4PRDA-51: an unacknowledged update is sent again, unchanged, 30 seconds after it was sent.
import app
from nrvv_env import SendCall, Simulation

SEEDS = (1, 2, 3, 4, 5)
STATION = 'S1'


def _outstanding_update(seed):
    # No copy of any update reaches the station (loss_rate=1.0), so nothing is acknowledged
    # and the first update stays the only outstanding one.
    sim = Simulation(seed, server=app, stations=[STATION], change_rate=0.3, loss_rate=1.0, outages=False)
    while not sim.send_calls:
        assert sim.now < sim.horizon, 'server never sent an update'
        sim.step()
    first = sim.send_calls[0]
    assert sim.now == first.time
    return sim, first


def test_no_resend_before_30_seconds_without_acknowledgement():
    for seed in SEEDS:
        sim, first = _outstanding_update(seed)
        for elapsed in range(1, 30):
            sim.step()
            assert sim.now == first.time + elapsed
            station_calls = [c for c in sim.send_calls if c.station_id == STATION]
            assert station_calls == [first], f'seed {seed}: send at {elapsed} s'
        assert not sim.ack_calls
        assert not sim.stations[STATION].received


def test_same_update_resent_at_30_seconds_without_acknowledgement():
    for seed in SEEDS:
        sim, first = _outstanding_update(seed)
        sim.run(30)
        assert sim.now == first.time + 30
        station_calls = [c for c in sim.send_calls if c.station_id == STATION]
        resend = SendCall(first.time + 30, STATION, first.sequence_number, first.price)
        assert station_calls == [first, resend], f'seed {seed}'
        assert not sim.ack_calls
