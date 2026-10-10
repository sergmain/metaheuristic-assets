"""GASV4RDF1-47: an acknowledgement showing the latest desired price confirms it for the station and sends exactly one pricing-team notice within one minute of receipt; an acknowledgement showing an older price sends no notice."""
import app
from nrvv_env import ACK_CHANNEL, NOTICE_BOUND, Simulation

SEEDS = (1, 2, 3, 5, 8)


def _new_sim(seed, max_delay=5):
    return Simulation(seed, app, min_delay=0, max_delay=max_delay)


def _read(entry, name):
    if isinstance(entry, dict):
        return entry[name]
    return getattr(entry, name)


def _unacknowledged_ids(sim):
    return [_read(entry, "station_id") for entry in sim.list_unacknowledged()]


def _received_at(sim, station_id, price):
    """Logical time at which the transport delivered the acknowledgement to app."""
    for event in sim.traffic:
        if (event["event"] == "delivered" and event["channel"] == ACK_CHANNEL
                and event["payload"]["station_id"] == station_id
                and event["payload"]["price"] == price):
            return event["t"]
    raise AssertionError(f"acknowledgement for {station_id!r} at {price!r} was never delivered")


def _notices_for(sim, station_id):
    return [n for n in sim.notices if n["station_id"] == station_id]


def test_latest_price_ack_confirms_price_and_sends_one_notice():
    sim = _new_sim(seed=1)
    station_id = "st-47-confirm"
    sim.add_station(station_id)
    sim.set_desired_price(station_id, 10)
    sim.acknowledge(station_id)
    sim.run_until_idle()

    assert len(sim.notices) == 1
    assert sim.notices[0]["station_id"] == station_id
    assert sim.notices[0]["price"] == 10
    assert len(sim.pricing.received) == 1
    assert sim.pricing.received[0]["station_id"] == station_id
    assert sim.pricing.received[0]["price"] == 10
    assert station_id not in _unacknowledged_ids(sim)


def test_notice_arrives_within_one_minute_of_ack_receipt():
    for seed in SEEDS:
        sim = _new_sim(seed=seed, max_delay=5)
        station_id = f"st-47-bound-{seed}"
        price = 100 + seed
        sim.add_station(station_id)
        sim.set_desired_price(station_id, price)
        sim.advance_time(seed * 3)
        sim.acknowledge(station_id)
        sim.run_until_idle()

        assert len(sim.pricing.received) == 1
        received_at = _received_at(sim, station_id, price)
        arrived_at = sim.pricing.received[0]["arrived_at"]
        assert arrived_at is not None
        assert arrived_at - received_at <= NOTICE_BOUND
        assert sim.late_notices() == []


def test_repeated_latest_ack_does_not_duplicate_notice():
    for seed in SEEDS:
        sim = _new_sim(seed=seed)
        station_id = f"st-47-repeat-{seed}"
        sim.add_station(station_id)
        sim.set_desired_price(station_id, 20)
        sim.acknowledge(station_id)
        sim.run_until_idle()
        sim.acknowledge(station_id)
        sim.run_until_idle()
        sim.acknowledge(station_id)
        sim.run_until_idle()

        notices = _notices_for(sim, station_id)
        assert len(notices) == 1
        assert notices[0]["price"] == 20
        assert len(sim.pricing.received) == 1


def test_older_price_ack_after_latest_sends_no_notice():
    for seed in SEEDS:
        sim = _new_sim(seed=seed)
        station_id = f"st-47-older-{seed}"
        sim.add_station(station_id)
        sim.set_desired_price(station_id, 30)
        sim.acknowledge(station_id)
        sim.run_until_idle()
        sim.set_desired_price(station_id, 31)
        sim.acknowledge(station_id)
        sim.run_until_idle()

        assert [n["price"] for n in _notices_for(sim, station_id)] == [30, 31]
        notices_before = len(sim.notices)
        received_before = len(sim.pricing.received)

        sim.transport.send(ACK_CHANNEL, {"station_id": station_id, "price": 30})
        sim.run_until_idle()

        assert len(sim.notices) == notices_before
        assert len(sim.pricing.received) == received_before


def test_each_station_latest_ack_gets_its_own_notice():
    sim = _new_sim(seed=13)
    first, second = "st-47-multi-a", "st-47-multi-b"
    sim.add_station(first)
    sim.add_station(second)
    sim.set_desired_price(first, 40)
    sim.set_desired_price(second, 41)
    sim.acknowledge(first)
    sim.acknowledge(second)
    sim.run_until_idle()

    assert sorted((n["station_id"], n["price"]) for n in sim.pricing.received) == [(first, 40), (second, 41)]
    assert first not in _unacknowledged_ids(sim)
    assert second not in _unacknowledged_ids(sim)
