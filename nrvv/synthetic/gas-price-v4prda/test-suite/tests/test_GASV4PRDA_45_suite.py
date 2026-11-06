# GASV4PRDA-45: a resend of the outstanding update keeps its price, and no older price is sent after a newer one.
import app
from nrvv_env import Simulation

STATION = 'S1'
# (P1, P2) pairs: P1 is the outstanding price, P2 the newer one set before the acknowledgement.
PRICE_PAIRS = [(10, 20), (30, 50), (40, 10)]
SEEDS = [1, 2, 3]


def _simulation(seed, p1, p2):
    # No scripted changes, duplicates or outages: only the send port and logical time matter here.
    # Every copy of an update is lost, so the outstanding update stays unacknowledged until the test acknowledges it.
    return Simulation(
        seed,
        app,
        stations=[STATION],
        prices=(p1, p2),
        change_rate=0,
        loss_rate=1.0,
        duplicate_rate=0,
        outages=False,
    )


def _assert_no_p1_after_p2(sim, p1, p2):
    newer_sent = False
    for call in sim.send_calls:
        if call.price == p2:
            newer_sent = True
        elif call.price == p1:
            assert not newer_sent, f'price {p1} sent at t={call.time} after {p2} was sent'


def _resend_scenario(seed, p1, p2):
    sim = _simulation(seed, p1, p2)
    sim.run(1)
    app.desired_price_change(STATION, p1)
    sim.run(1)
    fresh = [c for c in sim.send_calls if c.price == p1]
    assert fresh, 'no fresh update carried the first desired price'
    seq = fresh[0].sequence_number

    app.desired_price_change(STATION, p2)
    deadline = sim.now + 90
    while len(sim.send_calls) < 2 and sim.now < deadline:
        sim.step()
    assert len(sim.send_calls) >= 2, 'outstanding update was not resent'
    resend = sim.send_calls[1]
    assert resend.price == p1, f'resend carries {resend.price}, expected {p1}'
    assert resend.sequence_number == seq, 'resend does not carry the outstanding sequence number'
    _assert_no_p1_after_p2(sim, p1, p2)
    return sim, seq


def test_resend_keeps_outstanding_price_and_never_sends_older_after_newer():
    for seed, (p1, p2) in zip(SEEDS, PRICE_PAIRS):
        _resend_scenario(seed, p1, p2)


def test_fresh_update_after_ack_carries_newest_price_not_older_one():
    for seed, (p1, p2) in zip(SEEDS, PRICE_PAIRS):
        sim, seq = _resend_scenario(seed, p1, p2)
        app.acknowledgement_received(STATION, seq)
        before = len(sim.send_calls)
        sim.run(2)
        fresh = sim.send_calls[before:]
        assert fresh, 'no fresh update was sent after the acknowledgement'
        assert fresh[0].price == p2, f'fresh update carries {fresh[0].price}, expected {p2}'
        assert fresh[0].sequence_number != seq, 'fresh update reuses the acknowledged sequence number'
        assert all(c.price != p1 for c in fresh), f'fresh update carries superseded price {p1}'
        _assert_no_p1_after_p2(sim, p1, p2)
