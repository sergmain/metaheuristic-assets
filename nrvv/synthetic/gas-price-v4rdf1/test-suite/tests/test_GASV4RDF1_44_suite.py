'''Tests for GASV4RDF1-4 (keep updating a station until the latest price is confirmed), case GASV4RDF1-44.

The driver withholds acknowledgements: none is delivered until the station has received four updates, so the
first three attempts stay unacknowledged. The station queues one acknowledgement per received update and all
updates carry 1.499, so the acknowledgement delivered for the fourth attempt carries 1.499.
'''

import app
from nrvv_env import Simulation

STATION = 'S1'
PRICE = 1.499
SEEDS = (1, 2, 3)
MAX_STEPS = 200
WITHHELD = 3


def _delivered(sim):
    return len(sim.sent_log) - len(sim.in_flight())


def _drive(seed):
    sim = Simulation(app, seed, stations=(STATION,), script=[(STATION, PRICE)])
    sim.step_no += 1
    sim._issue_call()
    ack_step = None
    for _ in range(MAX_STEPS):
        if ack_step is None and _delivered(sim) > WITHHELD:
            sim.step_no += 1
            sim._deliver_ack()
            ack_step = sim.step_no
        elif sim.in_flight():
            sim.step_no += 1
            sim._deliver_update()
        else:
            break
    return sim, ack_step


def test_sends_latest_price_on_each_of_first_four_attempts():
    for seed in SEEDS:
        sim, ack_step = _drive(seed)
        assert ack_step is not None, 'seed %d: service stopped before an acknowledgement for 1.499 was received' % seed
        sends = [s for s in sim.sent_log if s.station == STATION and s.step < ack_step]
        assert len(sends) >= 4, 'seed %d: only %d updates sent before the fourth acknowledgement' % (seed, len(sends))
        assert [s.price for s in sends[:4]] == [PRICE] * 4, 'seed %d: first four updates carried %r' % (seed, [s.price for s in sends[:4]])
        assert sim.ack_log and sim.ack_log[-1].price == PRICE, 'seed %d: acknowledged price %r' % (seed, sim.ack_log[-1].price)


def test_no_update_sent_after_fourth_acknowledgement():
    for seed in SEEDS:
        sim, ack_step = _drive(seed)
        assert ack_step is not None, 'seed %d: service stopped before an acknowledgement for 1.499 was received' % seed
        late = [s for s in sim.sent_log if s.station == STATION and s.step > ack_step]
        assert late == [], 'seed %d: updates sent after the fourth acknowledgement: %r' % (seed, late)
