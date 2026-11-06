'''GASV4ACCK-34 / GASV4ACCK-5: the server records, per station, the price carried by the update
that station last acknowledged.

Every run drives app through nrvv_env. After each logical step the recorded price of each
station is compared with the price of the update whose acknowledgement the environment has
delivered so far (acknowledgements are in send order, one outstanding update per station).
'''

import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5, 6)
_ACK_NAMES = ('last_acknowledged_price', 'last_acknowledged', 'acknowledged_price',
              'last_acked_price', 'last_acked')


def _make_server():
    for name in dir(app):
        obj = getattr(app, name)
        if isinstance(obj, type) and obj.__module__ == app.__name__ and hasattr(obj, 'set_latest_price'):
            return obj()
    return app


def _fields(view):
    if isinstance(view, dict):
        return dict(view)
    names = [n for n in dir(view) if not n.startswith('_') and not callable(getattr(view, n))]
    return {n: getattr(view, n) for n in names}


def _last_acked(server, station):
    fields = _fields(server.get_station_view(station))
    for name in _ACK_NAMES:
        if name in fields:
            return fields[name]
    matches = [k for k in fields
               if 'ack' in k.lower() and 'time' not in k.lower() and 'outstanding' not in k.lower()]
    assert len(matches) == 1, f'cannot find the last-acknowledged price in the view of {station!r}: {fields!r}'
    return fields[matches[0]]


def _drive(seed, stations):
    '''Run one seeded environment and check the recorded price of every station after each step.'''
    sim = Simulation(seed, stations, changes_per_station=(2, 4), price_range=(1, 1000))
    server = sim.bind(_make_server())
    seen = {s: 0 for s in stations}   # acknowledgements already checked, per station
    last = {s: None for s in stations}  # price of the last acknowledged update, per station
    result = {'transitions': {s: 0 for s in stations}, 'held': {s: 0 for s in stations}}
    while sim.now <= sim.end_time or sim.in_flight:
        assert sim.now < 20000, 'simulation did not finish'
        sim.step()
        counts = {s: len(sim.stations[s].acknowledgements) for s in stations}
        gained = [s for s in stations if counts[s] > seen[s]]
        for s in stations:
            if counts[s] == seen[s]:
                if last[s] is not None and any(g != s for g in gained):
                    actual = _last_acked(server, s)
                    assert actual == last[s], (
                        f'station {s}: an acknowledgement from another station changed the recorded '
                        f'price to {actual!r}, expected {last[s]!r} (seed {seed}, t={sim.now - 1})')
                    result['held'][s] += 1
                continue
            sent = [r.price for r in sim.sends if r.station == s]
            assert counts[s] <= len(sent), f'station {s} acknowledged more updates than were sent'
            expected = sent[counts[s] - 1]
            actual = _last_acked(server, s)
            assert actual == expected, (
                f'station {s}: after acknowledgement {counts[s]} the recorded price is {actual!r}, '
                f'expected {expected!r} (seed {seed}, t={sim.now - 1})')
            if last[s] is not None and expected != last[s]:
                result['transitions'][s] += 1
            last[s] = expected
            seen[s] = counts[s]
    result['final'] = last
    return result


def test_recorded_price_is_p1_after_first_ack_then_p2_after_second_ack():
    transitions = 0
    for seed in SEEDS:
        transitions += _drive(seed, ['S', 'T'])['transitions']['S']
    assert transitions > 0, 'no seed gave station S two acknowledged updates with different prices'


def test_acknowledgement_from_other_station_leaves_recorded_price_unchanged():
    held = 0
    for seed in SEEDS:
        held += _drive(seed, ['S', 'T'])['held']['S']
    assert held > 0, 'no seed had an acknowledgement from T while S had a recorded price'


def test_recorded_price_tracks_every_acknowledgement_with_three_stations():
    transitions = {s: 0 for s in 'ABC'}
    for seed in (7, 8, 9, 10, 11, 12):
        result = _drive(seed, ['A', 'B', 'C'])
        for s in 'ABC':
            transitions[s] += result['transitions'][s]
    assert all(count > 0 for count in transitions.values()), transitions


def test_final_recorded_price_is_price_of_last_acknowledged_update():
    checked = 0
    for seed in SEEDS:
        sim = Simulation(seed, ['S', 'T'], changes_per_station=(2, 4), price_range=(1, 1000))
        server = sim.bind(_make_server())
        while sim.now <= sim.end_time or sim.in_flight:
            assert sim.now < 20000, 'simulation did not finish'
            sim.step()
        for s in ('S', 'T'):
            acked = len(sim.stations[s].acknowledgements)
            if acked == 0:
                continue
            sent = [r.price for r in sim.sends if r.station == s]
            assert _last_acked(server, s) == sent[acked - 1], (
                f'station {s}: final recorded price does not match the last acknowledged update (seed {seed})')
            checked += 1
    assert checked > 0, 'no station received an acknowledgement in any seed'
