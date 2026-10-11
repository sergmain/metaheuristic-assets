"""Requirement GASV4ACCJ-3: a new desired price is accepted while earlier updates are unacknowledged."""

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5)


def _assert_accepted(result, where):
    assert result is not None, where + ': no result returned'
    assert result is not False, where + ': rejected'
    if isinstance(result, str):
        lowered = result.lower()
        assert 'reject' not in lowered and 'error' not in lowered, where + ': ' + repr(result)
    if isinstance(result, dict):
        assert not result.get('rejected'), where + ': rejected ' + repr(result)
        assert not result.get('error'), where + ': error ' + repr(result)
        if 'accepted' in result:
            assert result['accepted'] is True, where + ': not accepted ' + repr(result)
    elif hasattr(result, 'accepted'):
        assert result.accepted is True, where + ': not accepted ' + repr(result)


def _unacknowledged(sim, station):
    return any(r.station == station and r.state in ('in_transit', 'delivered') for r in sim.sends())


def test_new_price_accepted_while_earlier_update_unacknowledged():
    for seed in SEEDS:
        station = 'STN-' + str(seed)
        sim = Simulation(seed, stations=(station,), changes=0)
        sim.connect(app)
        _assert_accepted(app.set_desired_price(station, 150), 'seed ' + str(seed) + ' first price')
        # The server decides when to send; advance only until one update to the station is out and unacknowledged.
        while not _unacknowledged(sim, station):
            assert sim.step(), 'seed ' + str(seed) + ': no update was sent to ' + station
        earlier = [r for r in sim.sends() if r.station == station and r.state in ('in_transit', 'delivered')]
        assert earlier, 'seed ' + str(seed) + ': no unacknowledged update'
        now = sim.now
        result = app.set_desired_price(station, 175)
        _assert_accepted(result, 'seed ' + str(seed) + ' new price')
        assert sim.now == now, 'seed ' + str(seed) + ': the call advanced simulated time, so it waited'
        assert all(r.state in ('in_transit', 'delivered') for r in earlier), 'seed ' + str(seed) + ': earlier update was acknowledged during the call'


def test_scheduled_price_changes_are_never_rejected_during_unacknowledged_sends():
    overlapping = 0
    for seed in SEEDS:
        stations = ('A' + str(seed), 'B' + str(seed), 'C' + str(seed))
        sim = Simulation(seed, stations=stations)
        sim.connect(app)
        sim.run_until_quiet()
        sends = sim.sends()
        for change in sim.changes():
            _assert_accepted(change.result, 'seed ' + str(seed) + ' change at ' + str(change.time))
            overlapping += sum(
                1 for r in sends
                if r.station == change.station and r.state == 'acked' and r.sent_at <= change.time < r.ack_arrived_at)
    assert overlapping > 0, 'no price change arrived while an earlier update was unacknowledged'
