import nrvv_env
import app

SEEDS = (1, 2, 3, 5, 8, 13, 21, 34)


def _is_success(result):
    if result is None or result is False or isinstance(result, BaseException):
        return False
    if isinstance(result, tuple) and result and result[0] is False:
        return False
    if isinstance(result, str):
        return not any(word in result.lower() for word in ('reject', 'error', 'fail'))
    if isinstance(result, dict):
        if result.get('accepted') is False:
            return False
        return not (result.get('error') or result.get('rejected'))
    return True


def _pending_ack_changes(sim):
    pairs = []
    for change in sim.changes:
        earlier = [s for s in sim.sends if s.station_id == change.station_id and s.sent_at < change.time]
        if earlier and earlier[-1].outcome == 'delivered' and earlier[-1].ack_at > change.time:
            pairs.append((change, earlier[-1]))
    return pairs


def test_new_price_accepted_while_earlier_update_unacknowledged():
    checked = 0
    for seed in SEEDS:
        sim = nrvv_env.Simulation(seed, app)
        sim.run_until_idle()
        for change, earlier in _pending_ack_changes(sim):
            checked += 1
            assert _is_success(change.result), (seed, change.result)
            acked_before = [a for a in sim.acks if a.send_id == earlier.send_id and a.time <= change.time]
            assert not acked_before, (seed, change)
            assert earlier.ack_at > change.time, (seed, change, earlier)
    assert checked > 0, 'no new price was submitted while an earlier update was unacknowledged'


def test_new_price_never_rejected_while_earlier_update_unacknowledged_across_loss_rates():
    checked = 0
    for seed in SEEDS:
        for loss_rate in (0.0, 0.1, 0.3):
            sim = nrvv_env.Simulation(seed, app, loss_rate=loss_rate)
            sim.run_until_idle()
            for change, earlier in _pending_ack_changes(sim):
                checked += 1
                assert _is_success(change.result), (seed, loss_rate, change.result)
    assert checked > 0, 'no new price was submitted while an earlier update was unacknowledged'
