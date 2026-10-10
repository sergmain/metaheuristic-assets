'''GASV4RDF1-54 / GASV4RDF1-39: the service notifies the pricing team within one minute of
receiving an acknowledgement that a station displays its latest desired price.'''
import app
from nrvv_env import ACK_CHANNEL, NOTICE_BOUND, NOTICE_CHANNEL, Simulation

SEEDS = [0, 1, 2, 3, 4]


def _receipt_time(sim, station_id, price):
    times = [
        ev['t']
        for ev in sim.traffic
        if ev['event'] == 'delivered'
        and ev['channel'] == ACK_CHANNEL
        and ev['payload'] == {'station_id': station_id, 'price': price}
    ]
    assert times, f'no acknowledgement of {price} from {station_id} was received'
    return times[0]


def _issued_within_bound(sim, station_id, price, receipt):
    return [
        n for n in sim.notices
        if n['station_id'] == station_id
        and n['price'] == price
        and receipt <= n['sent_at'] <= receipt + NOTICE_BOUND
    ]


def test_notice_issued_within_bound_after_ack_receipt():
    for seed in SEEDS:
        sim = Simulation(seed, app, min_delay=0, max_delay=5)
        sid = f'A-{seed}'
        price = 100 + seed
        sim.add_station(sid)
        sim.set_desired_price(sid, price)
        sim.acknowledge(sid)
        sim.run_until_idle()
        receipt = _receipt_time(sim, sid, price)
        assert _issued_within_bound(sim, sid, price, receipt), (
            f'seed {seed}: no notice issued within {NOTICE_BOUND} of receipt at t={receipt}; '
            f'notices={sim.notices}'
        )


def test_notice_names_station_and_confirmed_price_and_reaches_pricing_team():
    sim = Simulation(11, app, min_delay=0, max_delay=5)
    sim.add_station('B-1')
    sim.set_desired_price('B-1', 250)
    sim.acknowledge('B-1')
    sim.run_until_idle()
    assert any(n['station_id'] == 'B-1' and n['price'] == 250 for n in sim.notices), sim.notices
    assert any(ev['event'] == 'sent' and ev['channel'] == NOTICE_CHANNEL for ev in sim.traffic)
    assert any(n['station_id'] == 'B-1' and n['price'] == 250 for n in sim.pricing.received), sim.pricing.received


def test_every_station_notice_within_bound_after_its_receipt():
    for seed in SEEDS:
        sim = Simulation(seed, app, min_delay=0, max_delay=5)
        prices = {}
        for i in range(4):
            sid = f'C-{seed}-{i}'
            prices[sid] = 300 + 10 * i + seed
            sim.add_station(sid)
            sim.set_desired_price(sid, prices[sid])
            sim.acknowledge(sid)
        sim.run_until_idle()
        for sid, price in prices.items():
            receipt = _receipt_time(sim, sid, price)
            assert _issued_within_bound(sim, sid, price, receipt), (
                f'seed {seed}: station {sid} price {price}: no notice within {NOTICE_BOUND} of receipt at t={receipt}; '
                f'notices={sim.notices}'
            )


def test_bound_counts_from_receipt_when_transport_delay_is_long():
    for seed in SEEDS:
        sim = Simulation(seed, app, min_delay=50, max_delay=59)
        sid = f'D-{seed}'
        price = 400 + seed
        sim.add_station(sid)
        sim.set_desired_price(sid, price)
        sim.acknowledge(sid)
        sim.advance_time(25)
        sim.run_until_idle()
        receipt = _receipt_time(sim, sid, price)
        assert _issued_within_bound(sim, sid, price, receipt), (
            f'seed {seed}: no notice within {NOTICE_BOUND} of receipt at t={receipt}; '
            f'notices={sim.notices}'
        )


def test_each_new_price_notified_within_bound_after_its_receipt():
    sim = Simulation(21, app, min_delay=0, max_delay=5)
    sid = 'E-1'
    sim.add_station(sid)
    for price in (100, 120, 140):
        sim.set_desired_price(sid, price)
        sim.acknowledge(sid)
        sim.run_until_idle()
        sim.advance_time(1000)
    for price in (100, 120, 140):
        receipt = _receipt_time(sim, sid, price)
        assert _issued_within_bound(sim, sid, price, receipt), (
            f'price {price}: no notice within {NOTICE_BOUND} of receipt at t={receipt}; '
            f'notices={sim.notices}'
        )
