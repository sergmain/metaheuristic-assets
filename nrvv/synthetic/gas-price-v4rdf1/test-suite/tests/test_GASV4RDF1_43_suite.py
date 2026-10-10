'''Tests for GASV4RDF1-14 (keep resending until a matching acknowledgement arrives), case GASV4RDF1-43.

Each seeded run drives the server through nrvv_env. Before and after every call and every acknowledgement the
tests read the environment's ground truth (updates in flight, updates received but not yet acknowledged, the
last acknowledged price, the desired price) and check the criterion against what the server sent in that step.
'''

import importlib

import app
from nrvv_env import Simulation

SEEDS = range(40)
PRICES = (1, 3)
CALLS = 12


def _outstanding(sim, station, price):
    in_flight = sum(1 for s, p in sim.in_flight() if s == station and p == price)
    received = sum(1 for p in sim.stations[station].acks if p == price)
    return in_flight + received


def _record_events(seed):
    # reload gives each run a fresh server state
    module = importlib.reload(app)
    sim = Simulation(module, seed, calls=CALLS, prices=PRICES)
    events = []
    while True:
        names = list(sim.stations)
        confirmed = {n: sim.last_ack_price(n) for n in names}
        outstanding = {(n, p): _outstanding(sim, n, p)
                       for n in names for p in range(PRICES[0], PRICES[1] + 1)}
        n_calls, n_acks, n_sent = len(sim.call_log), len(sim.ack_log), len(sim.sent_log)
        if not sim.step():
            break
        if len(sim.call_log) > n_calls:
            kind = 'call'
            station, price = sim.call_log[-1].station, sim.call_log[-1].price
        elif len(sim.ack_log) > n_acks:
            kind = 'ack'
            station, price = sim.ack_log[-1].station, sim.ack_log[-1].price
        else:
            continue
        desired = sim.desired[station]
        sent = [x for x in sim.sent_log[n_sent:] if x.station == station and x.price == desired]
        events.append({
            'seed': seed,
            'kind': kind,
            'station': station,
            'price': price,
            'desired': desired,
            'confirmed': confirmed[station],
            'outstanding': outstanding[(station, desired)],
            'sent': len(sent),
        })
    return events, sim


def _describe(event):
    return 'event=%r' % (event,)


def test_new_price_is_sent_when_confirmed_price_differs():
    checked = 0
    for seed in SEEDS:
        events, _ = _record_events(seed)
        for e in events:
            if (e['kind'] == 'call' and e['confirmed'] is not None
                    and e['confirmed'] != e['desired'] and e['outstanding'] == 0):
                checked += 1
                assert e['sent'] >= 1, _describe(e)
    assert checked > 0


def test_ack_leaving_confirmed_price_different_from_desired_triggers_at_most_one_resend():
    checked = 0
    for seed in SEEDS:
        events, _ = _record_events(seed)
        for e in events:
            if e['kind'] == 'ack' and e['price'] != e['desired'] and e['outstanding'] == 0:
                checked += 1
                assert e['sent'] <= 1, _describe(e)
    assert checked > 0


def test_ack_setting_confirmed_price_to_desired_triggers_no_resend():
    checked = 0
    for seed in SEEDS:
        events, _ = _record_events(seed)
        for e in events:
            if e['kind'] == 'ack' and e['price'] == e['desired']:
                checked += 1
                assert e['sent'] == 0, _describe(e)
    assert checked > 0


def test_no_additional_update_carrying_desired_price_while_one_is_outstanding():
    checked = 0
    for seed in SEEDS:
        events, _ = _record_events(seed)
        for e in events:
            if e['outstanding'] >= 1:
                checked += 1
                assert e['sent'] == 0, _describe(e)
    assert checked > 0


def test_resending_ends_with_station_confirming_latest_desired_price():
    runs = 0
    for seed in SEEDS:
        _, sim = _record_events(seed)
        for station, price in sim.desired.items():
            runs += 1
            assert sim.last_ack_price(station) == price, (
                'seed=%r station=%r desired=%r last_ack=%r'
                % (seed, station, price, sim.last_ack_price(station)))
    assert runs > 0
